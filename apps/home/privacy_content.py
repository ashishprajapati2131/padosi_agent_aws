"""Built-in privacy policy used to seed the database and to keep /privacy/ online
when no row is published."""
from datetime import date
from types import SimpleNamespace

COMPANY_NAME = "PadosiAgent ServTech Private Limited"
ADDRESS = "Ahmedabad, Gujarat, India"
CONTACT_EMAIL = "support@padosiagent.com"
GRIEVANCE_EMAIL = "padosiagent@gmail.com"
EFFECTIVE_DATE = date(2026, 11, 27)

DEFAULT_PRIVACY_BODY = """
<p>PadosiAgent values your privacy. This policy explains what information the PadosiAgent website and app collect, why we collect it, who we share it with, how long we keep it, and how you can delete it. It is the policy linked from the website, from Play Console, and from Settings → Privacy Policy in the app.</p>

<div class="legal-compliance">
<h2>1. Legal basis</h2>
<p>This Privacy Policy is written for users in India and is meant to be read with:</p>
<ul class="no-list">
<li>The Information Technology Act, 2000</li>
<li>The Information Technology (Reasonable Security Practices and Procedures and Sensitive Personal Data or Information) Rules, 2011</li>
<li>The Digital Personal Data Protection Act, 2023</li>
</ul>
</div>

<h2>2. Who this policy covers</h2>
<ul class="no-list">
<li><strong>Website visitors and account holders</strong> who use padosiagent.com, including people who search for agents, create an account, or contact us.</li>
<li><strong>Agents:</strong> insurance professionals registered on PadosiAgent who sign in to the app or the website.</li>
<li><strong>Guests:</strong> people who are not registered agents and use the app's free sign-up to try Calculators and Reminders. Guests must be 18 or older.</li>
</ul>

<h2>3. Information we collect</h2>
<div class="data-category">
<h3>3.1 Website</h3>
<p>When you use padosiagent.com we collect:</p>
<ul class="no-list">
<li><strong>Account details you submit:</strong> name, mobile number, email address, and pincode. A pincode is an area code. It is not a precise GPS location.</li>
<li><strong>Professional details you choose to add:</strong> PAN, licences, and certifications for verification, plus business details and profile content you publish.</li>
<li><strong>Technical data:</strong> IP address, device and browser details, cookies, and usage analytics.</li>
<li><strong>Payments:</strong> subscription payments are handled by third-party payment gateways. We do not store your card number.</li>
<li><strong>Messages you send us:</strong> contact-form and support messages.</li>
</ul>
</div>
<div class="data-category">
<h3>3.2 Agents</h3>
<p>When you register as a verified agent and use the app, we collect:</p>
<ul class="no-list">
<li><strong>Personal details:</strong> full name, email address, mobile number.</li>
<li><strong>Region details:</strong> state, city, local area, and pincode.</li>
<li><strong>Professional details:</strong> years of experience, languages, insurance companies you work with, services, and focus areas.</li>
<li><strong>Photos:</strong> profile photo and the documents or photos you upload for your verified badge, certificates, and achievements.</li>
<li><strong>Leads and reminders:</strong> details of clients and leads you receive or add (name, phone number, requirement, notes), lead status (New, Contacted, Closed), and follow-up reminders.</li>
<li><strong>Digital card and reviews:</strong> the details you put on your digital visiting card and reviews customers leave for you.</li>
</ul>
</div>
<div class="data-category">
<h3>3.3 Guests</h3>
<p>When you use the free sign-up we collect your <strong>name, mobile number, email address, and pincode</strong>. Your guest password is your mobile number. Guest reminders are stored only on your phone.</p>
</div>
<div class="data-category">
<h3>3.4 Social Media Manager (agents only, optional)</h3>
<p>If you connect Instagram, Facebook, WhatsApp, YouTube, or Google Business Profile, we process:</p>
<ul class="no-list">
<li><strong>Account connection details:</strong> account and page IDs, names, profile photos, and the access permission (token) you give when connecting. Tokens are stored on our servers and on the servers of our social media gateway, <strong>Artha</strong>. They are never stored in the app.</li>
<li><strong>Posts you create:</strong> captions, hashtags, schedules, and the photos or videos you upload. Uploaded files are stored on Google Cloud at a random link that cannot be guessed, so that the platform can download and publish them. After publishing, the post is public on that platform.</li>
<li><strong>Customer conversations:</strong> direct messages, comments, reviews, and leads from your customers on the connected accounts, so you can read and reply to them and run automatic replies you set up.</li>
<li><strong>Create with AI:</strong> the text you type is sent to an AI service, provided through Artha, to write a draft caption, hashtags, and a suggested time. Do not enter passwords, card numbers, or another person's sensitive information. Review every draft before you publish or send it. You remain responsible for what you use.</li>
</ul>
<p>You can disconnect a connected account at any time in the app (Social Media → Accounts). You must have the right to share the messages, posts, photos, and videos you submit. After content reaches a social platform, that platform handles it under its own privacy policy.</p>
</div>
<div class="data-category">
<h3>3.5 Feedback</h3>
<p>When you send feedback we store its title, your message, and any screenshot or photo you attach.</p>
</div>
<div class="data-category">
<h3>3.6 Information collected automatically in the app</h3>
<ul class="no-list">
<li><strong>Device and app identifiers:</strong> Firebase installation ID, push notification token and, on Android, the advertising ID read by Firebase Analytics.</li>
<li><strong>App usage:</strong> which screens and features you use, and how often.</li>
<li><strong>Diagnostics:</strong> crash reports and technical logs (device model, OS version, app version).</li>
<li><strong>App integrity:</strong> a check that requests come from the genuine app (Firebase App Check / Play Integrity).</li>
</ul>
</div>
<div class="highlight-box">
<p><strong>We do not collect your precise GPS location, your phone's contacts, call logs, or SMS.</strong> The Android advertising ID is used by Firebase Analytics to understand how the app is used. We do not use your data to show you advertising, and we do not sell your data.</p>
</div>

<h2>4. How we use information</h2>
<ul class="no-list">
<li>To provide the website and the app: sign-in, profile, leads, reminders, calculators, digital card, reviews, and the Social Media Manager.</li>
<li>To match local insurance enquiries to agents working in the same area.</li>
<li>To publish posts and send replies when you ask us to.</li>
<li>To send notifications about new leads, reminders, and account updates.</li>
<li>To take payments for plans you buy, through the payment gateway.</li>
<li>To keep the service secure and prevent misuse.</li>
<li>To understand which features are used and to fix crashes.</li>
<li>To answer your feedback and support requests, and to meet legal duties.</li>
</ul>
<div class="warning-box">
<p><span class="prohibited-item">We do not sell personal data, and we do not use it for advertising.</span></p>
</div>

<h2>5. Who we share information with</h2>
<p>We share information only with service providers that run the website and the app for us, and only for the purposes above:</p>
<ul class="no-list">
<li><strong>Google (Firebase and Google Cloud):</strong> hosting, database, file storage, push notifications, analytics, crash reporting, and app integrity.</li>
<li><strong>Artha,</strong> our social media gateway: connects to your social accounts, publishes posts, receives customer messages, and provides Create with AI. Used only when you connect an account or ask us to publish, reply, or draft a post.</li>
<li><strong>Social platforms you choose</strong> — Meta (Instagram, Facebook, WhatsApp) and Google (YouTube, Google Business Profile) — when you publish, reply, or connect an account. Their own privacy policies apply to content on their platforms.</li>
<li><strong>Payment gateways</strong> that process a plan you buy. They receive what is needed to take the payment. We do not store card data.</li>
<li><strong>Legal authorities,</strong> if required by law or to protect the rights and safety of our users and PadosiAgent.</li>
</ul>

<h2>6. How long we keep information</h2>
<ul class="no-list">
<li><strong>Agent and website account data:</strong> while your account is active, and deleted after you request account deletion, except what we must keep by law.</li>
<li><strong>Guest sign-up details:</strong> until you delete your guest account. They are deleted within 7 days of your request.</li>
<li><strong>Uploaded post photos and videos:</strong> deleted automatically from our storage 90 days after upload. The published post stays on the platform until you delete it there.</li>
<li><strong>Feedback:</strong> kept while we need it to respond to you and to improve the service, and for any longer period the law requires.</li>
<li><strong>Crash and analytics data:</strong> kept for the retention period configured in our Firebase project.</li>
<li><strong>Payment records:</strong> kept for as long as tax and accounting law requires.</li>
</ul>

<h2>7. Security</h2>
<div class="security-box">
<p>All data is sent over encrypted connections (HTTPS/TLS). Social media tokens and service keys are kept only on our servers. Access to feedback, guest sign-ups, and admin tools is limited to authorised PadosiAgent staff.</p>
<p>No system is completely secure. Please use a unique password for your agent account and do not share it.</p>
</div>

<h2>8. Cookies</h2>
<p>On the website, cookies are used for session management, analytics, and performance. Turning cookies off in your browser can limit sign-in and other features. The mobile app does not use browser cookies. It uses the app identifiers described above.</p>

<h2>9. Your choices and rights</h2>
<ul class="no-list">
<li><strong>Delete your account (agents):</strong> in the app go to Settings → Delete Account, or use our <a href="/delete-account/">account deletion page</a>.</li>
<li><strong>Delete your account (guests):</strong> on the guest home screen open the menu → Delete account. Your sign-up details are deleted within 7 days and your reminders are removed from the phone immediately.</li>
<li><strong>Disconnect social accounts:</strong> Social Media → Accounts → Disconnect.</li>
<li><strong>Notifications:</strong> turn them off in the app settings or your phone settings.</li>
<li><strong>Access or correct your data:</strong> edit your profile in the app or on the website, or email support@padosiagent.com.</li>
<li><strong>Withdraw consent:</strong> you may ask us to stop optional processing. We may refuse a request where the law requires us to keep the information.</li>
</ul>

<h2>10. Children</h2>
<div class="highlight-box">
<p><strong>The website and the app are for adults (18+).</strong> The app is meant for insurance professionals and for adult guests trying Calculators and Reminders. We do not knowingly collect data from children.</p>
</div>

<h2>11. Third-party links</h2>
<p>The website and the app may link to insurers, social platforms, and other sites. Those sites have their own privacy policies. PadosiAgent is not responsible for how they handle information after you leave our service.</p>

<h2>12. Changes to this policy</h2>
<p>If we change this policy we will update the effective date above, publish the new version on this page, and show the new version in the app.</p>

<div class="consent-section">
<h3>Your consent</h3>
<p>By using the PadosiAgent website or app, you agree to this policy. If you do not agree, do not create an account and do not use the app. Connecting a social account or using Create with AI is optional, and doing so is a request for the processing described for those tools.</p>
</div>
""".strip()


def fallback_policy():
    """Unsaved policy so /privacy/ still renders if every row is deleted."""
    return SimpleNamespace(
        title="Privacy Policy",
        effective_date=EFFECTIVE_DATE,
        company_name=COMPANY_NAME,
        address=ADDRESS,
        contact_email=CONTACT_EMAIL,
        grievance_email=GRIEVANCE_EMAIL,
        content=DEFAULT_PRIVACY_BODY,
        is_published=True,
        pk=None,
    )


def published_policy():
    from apps.home.models.privacy_policy import PrivacyPolicy

    row = (
        PrivacyPolicy.objects.filter(is_published=True)
        .order_by("-updated_at", "-id")
        .first()
    )
    return row or fallback_policy()
