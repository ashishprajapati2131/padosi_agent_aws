import os
import base64
import logging
from datetime import datetime
from typing import Optional
from jinja2 import Environment, FileSystemLoader
from sqlalchemy.orm import Session

from app.models.invoice import Invoice
from app.models.agent import Agent
from app.models.agent_subscription import AgentSubscription
from app.models.agent_profile import AgentProfile
from app.config import settings

logger = logging.getLogger("invoice_service")

# Gracefully attempt to import WeasyPrint
try:
    import weasyprint
    WEASYPRINT_AVAILABLE = True
except (ImportError, OSError) as e:
    logger.warning(f"WeasyPrint is not fully available or GTK is missing. Using fallback placeholder generator. Error: {e}")
    WEASYPRINT_AVAILABLE = False

class InvoiceService:
    @staticmethod
    def resolve_discount_folder(discount_percent: float, total_amount: float) -> str:
        """
        Determines the discount folder categorization based on discount rate.
        Matches App/Models/Invoice::resolveDiscountFolder in PHP Laravel.
        """
        if total_amount <= 1.00:
            return "1re"
        if discount_percent == 0:
            return "no_discount"
        if discount_percent == 10:
            return "10_percent"
        if discount_percent == 25:
            return "25_percent"
        if discount_percent == 50:
            return "50_percent"
        return "others"

    @staticmethod
    def calculate_discount_percent(db: Session, subscription: AgentSubscription, total_amount: float) -> float:
        """
        Calculates the discount percentage relative to full plan pricing.
        Matches App/Services/InvoiceService::calculateDiscountPercent in PHP Laravel.
        """
        if total_amount <= 1.00:
            return 99.9

        # Fetch pricing configurations from site settings
        starter_price = 2359.00
        prof_price = 8258.00
        
        try:
            from sqlalchemy import text
            result = db.execute(text("SELECT `value` FROM site_settings WHERE `key` = 'pricing'"))
            row = result.fetchone()
            if not row:
                result = db.execute(text("SELECT `value` FROM site_settings WHERE `key` = 'pricing_config'"))
                row = result.fetchone()
                
            if row and row[0]:
                import json
                config = json.loads(row[0])
                if "starter" in config and "full_price" in config["starter"]:
                    starter_price = float(config["starter"]["full_price"])
                if "professional" in config and "full_price" in config["professional"]:
                    prof_price = float(config["professional"]["full_price"])
        except Exception as e:
            logger.warning(f"Failed to fetch site settings pricing: {e}")

        plan_name = (subscription.selected_plan or "").lower()
        if "trial" in plan_name:
            return 0.0

        full_price = starter_price if ("starter" in plan_name or "basic" in plan_name) else prof_price
        if full_price <= 0:
            return 0.0

        discount = round(((full_price - total_amount) / full_price) * 100.0, 1)
        return max(0.0, discount)

    @staticmethod
    def generate_invoice_number(db: Session) -> str:
        """
        Generates a unique invoice number in the format: INV-YYYY-XXXXX
        """
        year = datetime.utcnow().year
        # Count current invoices for the year
        from sqlalchemy import text
        result = db.execute(
            text("SELECT COUNT(*) FROM invoices WHERE YEAR(created_at) = :year"),
            {"year": year}
        )
        count = result.scalar() + 1

        while True:
            number = f"INV-{year}-{str(count).zfill(5)}"
            # Verify uniqueness
            exists_result = db.execute(
                text("SELECT 1 FROM invoices WHERE invoice_number = :number"),
                {"number": number}
            )
            if not exists_result.fetchone():
                return number
            count += 1

    @staticmethod
    def generate_pdf_invoice(db: Session, invoice: Invoice) -> str:
        """
        Renders the invoice template using Jinja2 and compiles it into PDF via WeasyPrint.
        Saves PDF locally to: storage/app/invoices/{discount_folder}/{invoice_number}.pdf
        """
        # Load invoice template
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        template_dir = os.path.join(base_dir, "templates")
        
        env = Environment(loader=FileSystemLoader(template_dir))
        template = env.get_template("invoice_pdf.html")
        
        # Load and base64-encode company logo if it exists
        logo_base64 = ""
        # The public logo path is shared in the Laravel project directory structure
        public_logo_path = os.path.abspath(os.path.join(base_dir, "..", "..", "public", "img", "logo.png"))
        if os.path.exists(public_logo_path):
            try:
                with open(public_logo_path, "rb") as f:
                    logo_base64 = "data:image/png;base64," + base64.b64encode(f.read()).decode("utf-8")
            except Exception as logo_err:
                logger.warning(f"Could not encode logo image: {logo_err}")

        invoice_date_str = invoice.created_at.strftime("%d %b, %Y") if invoice.created_at else datetime.utcnow().strftime("%d %b, %Y")
        
        is_gujarat = "gujarat" in (invoice.agent_state or "").lower()
        
        font_path = os.path.abspath(os.path.join(base_dir, "..", "static", "fonts", "DejaVuSans.ttf")).replace('\\', '/')
        font_path_bold = os.path.abspath(os.path.join(base_dir, "..", "static", "fonts", "DejaVuSans-Bold.ttf")).replace('\\', '/')
        
        rendered_html = template.render(
            invoice=invoice,
            invoice_date=invoice_date_str,
            logo_src=logo_base64,
            is_gujarat=is_gujarat,
            font_path=font_path,
            font_path_bold=font_path_bold
        )

        # Define destination paths matching Laravel structure
        discount_folder = invoice.discount_folder or "others"
        storage_base = os.path.abspath(os.path.join(base_dir, "..", "storage"))
        invoice_dir = os.path.join(storage_base, "invoices", discount_folder)
        os.makedirs(invoice_dir, exist_ok=True)
        
        pdf_filename = f"{invoice.invoice_number}.pdf"
        target_pdf_path = os.path.join(invoice_dir, pdf_filename)
        
        try:
            from xhtml2pdf import pisa
            import tempfile
            
            # Temporary monkey-patch for xhtml2pdf Windows file-lock bug
            original_named_temp_file = tempfile.NamedTemporaryFile
            class ClosedNamedTemporaryFile:
                def __init__(self, *args, **kwargs):
                    kwargs['delete'] = False
                    self._file = original_named_temp_file(*args, **kwargs)
                    self.name = self._file.name
                    self._closed = False
                def write(self, data):
                    if not self._closed:
                        self._file.write(data)
                def flush(self):
                    if not self._closed:
                        self._file.flush()
                        self._file.close()
                        self._closed = True
                def close(self): pass
                def __del__(self):
                    try:
                        if os.path.exists(self.name):
                            os.remove(self.name)
                    except Exception:
                        pass
            tempfile.NamedTemporaryFile = ClosedNamedTemporaryFile
            
            try:
                with open(target_pdf_path, "w+b") as result_file:
                    pisa_status = pisa.CreatePDF(rendered_html, dest=result_file, encoding='utf-8')
            finally:
                tempfile.NamedTemporaryFile = original_named_temp_file
                
            if pisa_status.err:
                logger.error(f"xhtml2pdf PDF rendering failed for {invoice.invoice_number}")
                InvoiceService._write_fallback_file(target_pdf_path, rendered_html, invoice)
            else:
                logger.info(f"Successfully compiled xhtml2pdf PDF: {target_pdf_path}")
                
        except Exception as e:
            logger.error(f"xhtml2pdf PDF rendering failed, writing fallback: {e}")
            InvoiceService._write_fallback_file(target_pdf_path, rendered_html, invoice)
            
        # Return path relative to storage root for database logging matching Laravel
        relative_path = f"invoices/{discount_folder}/{pdf_filename}"
        return relative_path

    @staticmethod
    def _write_fallback_file(target_path: str, html_content: str, invoice: Invoice) -> None:
        """
        Compiles a standards-compliant PDF file using FPDF to ensure valid rendering when WeasyPrint/GTK is unavailable.
        """
        try:
            from fpdf import FPDF
            
            pdf = FPDF()
            pdf.add_page()
            
            # --- Header ---
            # Logo Icon
            pdf.set_draw_color(15, 86, 52) # Green
            pdf.set_fill_color(15, 86, 52)
            pdf.ellipse(15, 18, 6, 6, "F") # Outer circle
            pdf.set_fill_color(255, 255, 255)
            pdf.ellipse(17, 20, 2, 2, "F") # Inner white circle
            
            # Logo Text next to icon
            pdf.set_xy(23, 17.5)
            pdf.set_font("helvetica", "B", 16)
            pdf.set_text_color(24, 82, 157) # Blue
            pdf.write(7, "Padosi")
            pdf.set_text_color(15, 86, 52) # Green
            pdf.write(7, "Agent")
            
            # Company Details (Right side, right-aligned)
            def print_right_header(text, y_pos, is_bold=False, size=9, color=(106, 106, 106)):
                pdf.set_font("helvetica", "B" if is_bold else "", size)
                pdf.set_text_color(*color)
                pdf.set_xy(100, y_pos)
                pdf.cell(95, 4, text, ln=0, align="R")
            
            print_right_header("PadosiAgent ServTech Private", 16, is_bold=True, size=14, color=(24, 82, 157))
            print_right_header("Limited", 21.5, is_bold=True, size=14, color=(24, 82, 157))
            print_right_header("Your Trusted Technology", 27.5, is_bold=False, size=9)
            print_right_header("support@padosiagent.com | +91 9876543210", 32, is_bold=False, size=8.5)
            print_right_header("GSTIN: 24AAPCP4222R1ZV", 36.5, is_bold=False, size=8.5)
            
            # Divider Line below header
            pdf.set_draw_color(24, 82, 157)
            pdf.set_line_width(0.8)
            pdf.line(15, 42, 195, 42)
            
            # Faint background watermark "PAID"
            with pdf.rotation(angle=15, x=150, y=55):
                pdf.set_font("helvetica", "B", 38)
                pdf.set_text_color(235, 247, 238) # Very light faint green
                pdf.text(140, 55, "PAID")
            
            # --- Billing & Invoice metadata ---
            # Bill To Column (Left side)
            pdf.set_xy(15, 48)
            pdf.set_text_color(106, 106, 106)
            pdf.set_font("helvetica", "B", 9.5)
            pdf.cell(95, 5, "BILL TO", ln=1)
            
            pdf.set_xy(15, 54)
            pdf.set_text_color(26, 26, 26)
            pdf.set_font("helvetica", "B", 13)
            pdf.cell(95, 5, str(invoice.agent_name), ln=1)
            
            pdf.set_xy(15, 60.5)
            pdf.set_font("helvetica", "", 10)
            pdf.set_text_color(106, 106, 106)
            pdf.cell(95, 5, str(invoice.agent_email), ln=1)
            
            if invoice.agent_mobile:
                pdf.set_xy(15, 66.5)
                pdf.cell(95, 5, f"+91 {invoice.agent_mobile}", ln=1)
                
            y_bill = pdf.get_y()
            
            # Invoice Details Label (Right side, right-aligned)
            pdf.set_xy(100, 48)
            pdf.set_font("helvetica", "B", 9.5)
            pdf.set_text_color(106, 106, 106)
            pdf.cell(95, 5, "INVOICE DETAILS", ln=0, align="R")
            
            # Helper to print right-aligned key-value pairs
            def print_detail_pair(label, val, y_pos):
                lbl_w = pdf.get_string_width(f"{label}: ")
                val_w = pdf.get_string_width(val)
                start_x = 195 - lbl_w - val_w
                
                pdf.set_xy(start_x, y_pos)
                pdf.set_font("helvetica", "", 10)
                pdf.set_text_color(106, 106, 106)
                pdf.write(5, f"{label}: ")
                
                pdf.set_font("helvetica", "B", 10)
                pdf.set_text_color(26, 26, 26)
                pdf.write(5, val)
                
            print_detail_pair("Invoice Number", invoice.invoice_number, 54)
            print_detail_pair("Invoice Date", invoice.created_at.strftime("%d %b, %Y") if invoice.created_at else datetime.utcnow().strftime("%d %b, %Y"), 60.5)
            
            if invoice.razorpay_payment_id:
                print_detail_pair("Payment ID", invoice.razorpay_payment_id, 66.5)
                
            # PAID green badge (Right side)
            pdf.set_xy(177, 72.5)
            pdf.set_text_color(22, 163, 74) # Green #16a34a
            pdf.set_draw_color(34, 197, 94) # Green border #22c55e
            pdf.set_fill_color(240, 253, 244) # Light green bg #f0fdf4
            pdf.set_font("helvetica", "B", 9)
            pdf.cell(18, 6, "PAID", border=1, ln=1, align="C", fill=True)
            
            # --- Table of Services ---
            # Separator above table headers
            pdf.set_draw_color(24, 82, 157) # Blue
            pdf.set_line_width(0.6)
            pdf.line(15, 86, 195, 86)
            
            # Headers Background
            pdf.set_fill_color(248, 249, 250)
            pdf.rect(15, 87, 180, 10, "F")
            
            pdf.set_xy(15, 87)
            pdf.set_text_color(24, 82, 157)
            pdf.set_font("helvetica", "B", 9)
            pdf.cell(10, 10, "#", border=0, ln=0, align="C")
            pdf.cell(100, 10, "SERVICE DETAILS", border=0, ln=0, align="L")
            
            pdf.set_xy(125, 87)
            pdf.cell(45, 10, "BASE PRICE (EXCL. GST)", border=0, ln=0, align="R")
            
            pdf.set_xy(170, 87)
            pdf.cell(25, 10, "AMOUNT", border=0, ln=1, align="R")
            
            # Separator below table headers
            pdf.line(15, 97, 195, 97)
            
            # Row 1 values
            pdf.set_xy(15, 100)
            pdf.set_font("helvetica", "B", 10)
            pdf.set_text_color(26, 26, 26)
            pdf.cell(10, 5, "1", border=0, align="C")
            
            # Plan details text
            pdf.set_xy(25, 100)
            pdf.set_font("helvetica", "B", 10)
            pdf.cell(100, 5, str(invoice.plan_name), border=0, align="L")
            
            pdf.set_xy(25, 105.5)
            pdf.set_font("helvetica", "", 9)
            pdf.set_text_color(106, 106, 106)
            plan_desc = "PadosiAgent Subscription - 30 Day Trial" if invoice.plan_type == "free_trial" else ("PadosiAgent Subscription - 1 Year Starter" if invoice.plan_type == "basic" else "PadosiAgent Subscription - 1 Year Professional")
            pdf.cell(100, 5, plan_desc, border=0, align="L")
            
            row_end_y = 112
            if invoice.promo_code:
                pdf.set_xy(25, 111)
                pdf.set_font("helvetica", "B", 9)
                pdf.set_text_color(22, 163, 74) # Green
                pdf.cell(100, 5, f"Promo Applied: {invoice.promo_code}", border=0, align="L")
                row_end_y = 117
                
            # Base price and amount column values
            pdf.set_xy(125, 100)
            pdf.set_font("helvetica", "", 10)
            pdf.set_text_color(26, 26, 26)
            pdf.cell(45, 5, f"Rs. {invoice.base_amount:.2f}", border=0, align="R")
            
            pdf.set_xy(170, 100)
            pdf.cell(25, 5, f"Rs. {invoice.base_amount:.2f}", border=0, align="R")
            
            # Row bottom divider line
            pdf.set_draw_color(229, 231, 235)
            pdf.set_line_width(0.3)
            pdf.line(15, row_end_y, 195, row_end_y)
            
            # --- Totals Section ---
            totals_start_y = row_end_y + 8
            
            def add_total_row(label, val, y_pos):
                pdf.set_xy(115, y_pos)
                pdf.set_font("helvetica", "", 10)
                pdf.set_text_color(106, 106, 106)
                pdf.cell(45, 5, label, ln=0, align="R")
                pdf.set_font("helvetica", "", 10)
                pdf.set_text_color(26, 26, 26)
                pdf.cell(30, 5, val, ln=1, align="R")
                
            add_total_row("Base Amount:", f"Rs. {invoice.base_amount:.2f}", totals_start_y)
            
            is_gujarat = "gujarat" in (invoice.agent_state or "").lower()
            if not is_gujarat:
                add_total_row("GST @ 18% (IGST):", f"Rs. {invoice.gst_amount:.2f}", totals_start_y + 6.5)
                totals_line_y = totals_start_y + 14
            else:
                add_total_row("CGST @ 9%:", f"Rs. {invoice.gst_amount/2:.2f}", totals_start_y + 6.5)
                add_total_row("SGST @ 9%:", f"Rs. {invoice.gst_amount/2:.2f}", totals_start_y + 12.5)
                totals_line_y = totals_start_y + 20
                
            # Totals line divider
            pdf.set_draw_color(24, 82, 157)
            pdf.set_line_width(0.6)
            pdf.line(125, totals_line_y, 195, totals_line_y)
            
            # Total Amount Row
            pdf.set_xy(115, totals_line_y + 5)
            pdf.set_font("helvetica", "B", 12.5)
            pdf.set_text_color(26, 26, 26)
            pdf.cell(45, 10.5, "Total Amount:", ln=0, align="R")
            
            # Value box
            pdf.set_fill_color(240, 245, 252) # Light blue box background
            pdf.rect(162, totals_line_y + 5, 33, 10.5, "F")
            
            pdf.set_xy(162, totals_line_y + 5)
            pdf.set_text_color(24, 82, 157)
            pdf.set_font("helvetica", "B", 14)
            pdf.cell(33, 10.5, f"Rs. {invoice.total_amount:.2f}", border=0, ln=1, align="C")
            
            # Inclusive of GST label
            pdf.set_xy(115, totals_line_y + 17)
            pdf.set_font("helvetica", "", 8)
            pdf.set_text_color(153, 153, 153)
            pdf.cell(77, 4, f"*Inclusive of GST Rs. {invoice.gst_amount:.2f}", ln=1, align="R")
            
            # --- Footer ---
            pdf.set_xy(15, 236)
            pdf.set_font("helvetica", "B", 12)
            pdf.set_text_color(26, 26, 26)
            pdf.cell(180, 5, "Thank you for choosing PadosiAgent.", border=0, ln=1, align="C")
            
            pdf.set_xy(15, 242)
            pdf.set_font("helvetica", "", 9)
            pdf.set_text_color(106, 106, 106)
            pdf.cell(180, 4, "If you have any questions concerning this invoice, please contact support@padosiagent.com", border=0, ln=1, align="C")
            
            # Centered signature: Powered by PadosiAgent ServTech Pvt Ltd
            p1 = "Powered by "
            p2 = "PadosiAgent ServTech Pvt Ltd"
            pdf.set_font("helvetica", "", 9)
            pdf.set_text_color(106, 106, 106)
            w1 = pdf.get_string_width(p1)
            w2 = pdf.get_string_width(p2)
            start_x = 105 - (w1 + w2) / 2
            
            pdf.set_xy(start_x, 249)
            pdf.write(4, p1)
            pdf.set_font("helvetica", "B", 9)
            pdf.set_text_color(24, 82, 157)
            pdf.write(4, p2)
            
            # Save the compiled PDF binary stream
            pdf.output(target_path)
            
            # Validation: Verify file size and header
            if not os.path.exists(target_path) or os.path.getsize(target_path) == 0:
                raise FileNotFoundError(f"Generated PDF file is empty or missing: {target_path}")
                
            with open(target_path, "rb") as verify_f:
                header = verify_f.read(5)
                if header != b"%PDF-":
                    raise ValueError(f"File header mismatch. Expected %PDF-, got {header}")
                    
            logger.info(f"Successfully generated a valid standards-compliant FPDF PDF at: {target_path}")
            
        except Exception as err:
            logger.error(f"FPDF PDF generation failed: {err}")
            # Fallback to saving HTML with PDF extension if all else fails
            try:
                with open(target_path, "w", encoding="utf-8") as f:
                    f.write(f"--- INVOICE PLACEHOLDER (ALL PDF COMPILERS FAILED) ---\n")
                    f.write(f"Invoice Number: {invoice.invoice_number}\n")
                    f.write(f"Agent: {invoice.agent_name} ({invoice.agent_email})\n")
                    f.write(f"Total Amount: {invoice.total_amount} INR\n")
                    f.write(f"Plan Name: {invoice.plan_name}\n")
                    f.write(f"Payment ID: {invoice.razorpay_payment_id}\n")
                    f.write(f"\nHTML Source:\n{html_content}")
                logger.warning(f"Saved fallback text invoice to: {target_path}")
            except Exception as nested_err:
                logger.critical(f"Critical error writing emergency text fallback: {nested_err}")

    @staticmethod
    def generate_from_subscription(db: Session, agent: Agent, subscription: AgentSubscription) -> Optional[Invoice]:
        r"""
        Creates an Invoice record and generates a PDF document.
        Matches App\Services\InvoiceService::generateFromSubscription in PHP Laravel.
        """
        try:
            # Prevent duplicate invoice creation for the same payment transaction
            if subscription.razorpay_payment_id:
                from sqlalchemy import text
                existing_invoice = db.query(Invoice).filter(
                    Invoice.razorpay_payment_id == subscription.razorpay_payment_id
                ).first()
                if existing_invoice:
                    logger.info(f"Invoice already exists for payment: {subscription.razorpay_payment_id}")
                    return existing_invoice

            total_amount = float(subscription.registration_amount or 0.00)
            base_amount = round(total_amount / 1.18, 2)
            gst_amount = round(total_amount - base_amount, 2)

            discount_percent = InvoiceService.calculate_discount_percent(db, subscription, total_amount)
            discount_folder = InvoiceService.resolve_discount_folder(discount_percent, total_amount)

            # Query agent profile to retrieve address and state
            from app.repositories.profile_repository import ProfileRepository
            profile_repo = ProfileRepository(db)
            profile = profile_repo.get_by_agent_id(agent.id)

            invoice_number = InvoiceService.generate_invoice_number(db)

            invoice = Invoice(
                invoice_number=invoice_number,
                agent_id=agent.id,
                agent_name=agent.fullname,
                agent_email=agent.email,
                agent_mobile=agent.mobile,
                agent_address=profile.address if profile else "",
                agent_state=profile.state if profile else "Gujarat",
                plan_name=subscription.selected_plan,
                plan_type=agent.plan_type or "professional",
                base_amount=base_amount,
                gst_amount=gst_amount,
                total_amount=total_amount,
                discount_percent=discount_percent,
                discount_folder=discount_folder,
                promo_code=subscription.promo_code,
                razorpay_payment_id=subscription.razorpay_payment_id,
                razorpay_order_id=subscription.razorpay_order_id,
                payment_status="completed"
            )
            
            db.add(invoice)
            db.flush()

            # Compile PDF doc
            pdf_path = InvoiceService.generate_pdf_invoice(db, invoice)
            if pdf_path:
                invoice.pdf_path = pdf_path
                
            db.commit()
            return invoice
        except Exception as e:
            db.rollback()
            logger.error(f"Invoice generation failed: {e}")
            return None
