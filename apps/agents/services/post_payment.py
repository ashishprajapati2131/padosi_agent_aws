"""
Post-payment fulfillment that must not block Razorpay verify/activate.

Invoice PDF, welcome email, and Google Sheet sync can take tens of seconds.
The checkout JSON response has to return as soon as the subscription is marked
paid, otherwise the success message never reaches the browser.
"""
import logging
import os
import threading

from django.conf import settings
from django.db import close_old_connections, transaction

logger = logging.getLogger(__name__)


def queue_invoice_and_welcome(agent_id, subscription_id):
    """Run invoice + welcome email after the current DB transaction commits."""
    if not agent_id or not subscription_id:
        logger.error(
            'queue_invoice_and_welcome skipped: agent_id=%s subscription_id=%s',
            agent_id,
            subscription_id,
        )
        return

    agent_id = int(agent_id)
    subscription_id = int(subscription_id)

    def _start():
        thread = threading.Thread(
            target=_run_invoice_and_welcome,
            args=(agent_id, subscription_id),
            daemon=False,
            name=f'invoice-welcome-{agent_id}',
        )
        thread.start()

    try:
        if transaction.get_connection().in_atomic_block:
            transaction.on_commit(_start)
            return
    except Exception:
        logger.exception(
            'Could not attach invoice/welcome to on_commit for agent %s',
            agent_id,
        )
    _start()


def fulfill_invoice_and_welcome(agent, subscription):
    """Synchronous fulfillment used by the background worker (and tests)."""
    from apps.agents.services.brevo import email_service
    from apps.agents.services.invoice import invoice_service

    invoice = invoice_service.generate_from_subscription(
        agent,
        subscription,
        sync_sheet=False,
    )
    pdf_path = None
    if invoice and invoice.pdf_path:
        pdf_path = os.path.join(settings.MEDIA_ROOT, 'app', 'private', invoice.pdf_path)

    try:
        from apps.agents.services.account_auth import default_agent_temp_password

        email_service.send_welcome(
            to_email=agent.email,
            to_name=agent.fullname,
            temp_password=default_agent_temp_password(agent),
            plan_name=subscription.selected_plan,
            attachment_path=pdf_path,
        )
    except Exception:
        logger.exception('Welcome email failed for agent %s', getattr(agent, 'id', None))

    if invoice:
        try:
            invoice_service.sync_to_google_sheet(invoice)
        except Exception:
            logger.exception(
                'Google Sheet sync failed for invoice %s',
                getattr(invoice, 'invoice_number', None),
            )
    return invoice


def _run_invoice_and_welcome(agent_id, subscription_id, max_retries=2, retry_delay=2):
    """
    Monitored background fulfillment worker with retry logic and telemetry logging.
    """
    close_old_connections()
    from apps.agents.models import Agent, AgentSubscription, RegistrationActivityLog

    agent = Agent.objects.filter(pk=agent_id).first()
    subscription = AgentSubscription.objects.filter(pk=subscription_id).first()

    if not agent or not subscription:
        logger.error(
            'Invoice/welcome skipped: agent=%s subscription=%s missing',
            agent_id,
            subscription_id,
        )
        RegistrationActivityLog.log(
            'FULFILLMENT_ABORTED',
            agent=agent,
            subscription_id=subscription_id,
            extra_details={'reason': 'Agent or Subscription row not found'}
        )
        return

    RegistrationActivityLog.log(
        'FULFILLMENT_STARTED',
        agent=agent,
        subscription_id=subscription_id,
        extra_details={'plan': subscription.selected_plan}
    )

    last_error = None
    for attempt in range(1, max_retries + 2):
        try:
            invoice = fulfill_invoice_and_welcome(agent, subscription)
            invoice_num = getattr(invoice, 'invoice_number', None) if invoice else None
            sheet_synced = getattr(invoice, 'synced_to_sheet', False) if invoice else False
            RegistrationActivityLog.log(
                'FULFILLMENT_SUCCESS',
                agent=agent,
                subscription_id=subscription_id,
                extra_details={
                    'invoice_number': invoice_num,
                    'sheet_synced': sheet_synced,
                    'attempts': attempt
                }
            )
            logger.info(
                'Background invoice/welcome succeeded for agent %s (sub=%s, inv=%s, attempt=%s)',
                agent_id, subscription_id, invoice_num, attempt
            )
            return invoice
        except Exception as err:
            last_error = err
            logger.warning(
                'Background invoice/welcome attempt %s/%s failed for agent %s: %s',
                attempt, max_retries + 1, agent_id, err
            )
            if attempt <= max_retries:
                import time
                time.sleep(retry_delay)
                close_old_connections()

    logger.critical(
        'CRITICAL: Background invoice/welcome permanently failed for agent %s (sub=%s) after %s attempts: %s',
        agent_id, subscription_id, max_retries + 1, last_error,
        exc_info=True
    )
    RegistrationActivityLog.log(
        'FULFILLMENT_FAILED',
        agent=agent,
        subscription_id=subscription_id,
        extra_details={'error': str(last_error), 'attempts': max_retries + 1}
    )
    close_old_connections()

