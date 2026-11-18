"""
Invite & Share Studio service for Agent Dashboard.

Supports:
- Section 1: Review & Rating (Asking clients for 5-star reviews & testimonials)
- Section 2: Share on Social Media (Sharing digital visiting card & referral campaign offer)
- Multi-language support across all product languages
- Pre-drafted templates with dynamic placeholder replacement
"""
import json
import logging
import re
from urllib.parse import quote
from django.urls import reverse

logger = logging.getLogger(__name__)

_PROFILE_LABEL_RE = re.compile(
    r'(?i)(view\s+(my\s+)?(complete\s+)?profile|you can also view my complete profile|'
    r'प्रोफाइल\s*देखें|प्रोफाइल\s*पहा|પ્રોફાઇલ\s*જુઓ|'
    r'check my verified credentials|प्रोफाइल,\s*सेवाएं|પ્રોફાઇલ,\s*ક્લાયન્ટ)'
)

STUDIO_TEMPLATES = {
    'review': {
        'label': 'Review & Rating',
        'languages': {
            'en': {
                'label': 'English',
                'templates': [
                    {
                        'id': 'rev_en_1',
                        'title': '⭐ Client Review Request (Recommended)',
                        'text': (
                            "Hi! Thank you for trusting me as your insurance advisor.\n\n"
                            "Could you please take 30 seconds to share your valuable review and 5-star rating on my official PadosiAgent profile?\n\n"
                            "⭐ Leave your review here:\n"
                            "{{review_link}}\n\n"
                            "Your feedback helps me serve you and others even better!\n"
                            "— {{agent_name}}"
                        )
                    },
                    {
                        'id': 'rev_en_2',
                        'title': '⚡ Quick 30-Sec Rating',
                        'text': (
                            "Dear client, your experience matters to me!\n\n"
                            "Please rate my insurance service and share quick feedback on PadosiAgent:\n"
                            "⭐ Rate now: {{review_link}}\n\n"
                            "Thank you for your continuous support and trust.\n"
                            "— {{agent_name}}"
                        )
                    },
                    {
                        'id': 'rev_en_3',
                        'title': '🤝 Professional Service Feedback',
                        'text': (
                            "Hello, I strive to provide the best insurance guidance for you and your family.\n\n"
                            "If you're satisfied with my service, I would truly appreciate your rating and review on PadosiAgent:\n"
                            "{{review_link}}\n\n"
                            "Warm regards,\n"
                            "{{agent_name}}"
                        )
                    }
                ]
            },
            'hi': {
                'label': 'हिन्दी (Hindi)',
                'templates': [
                    {
                        'id': 'rev_hi_1',
                        'title': '⭐ समीक्षा और रेटिंग अनुरोध (अनुशंसित)',
                        'text': (
                            "नमस्ते! अपने बीमा सलाहकार के रूप में मुझ पर विश्वास करने के लिए धन्यवाद।\n\n"
                            "कृपया PadosiAgent पर मेरी आधिकारिक प्रोफाइल पर 30 सेकंड निकालकर अपना बहुमूल्य रिव्यू और 5-स्टार रेटिंग दें:\n\n"
                            "⭐ रिव्यू यहाँ दें:\n"
                            "{{review_link}}\n\n"
                            "आपकी प्रतिक्रिया मुझे और बेहतर सेवा देने में मदद करती है!\n"
                            "— {{agent_name}}"
                        )
                    },
                    {
                        'id': 'rev_hi_2',
                        'title': '⚡ त्वरित 5-स्टार रेटिंग',
                        'text': (
                            "नमस्ते, आपका अनुभव मेरे लिए अत्यंत महत्वपूर्ण है!\n\n"
                            "कृपया PadosiAgent पर मेरी सेवा को रेट करें और अपना अनुभव साझा करें:\n"
                            "⭐ अभी रेट करें: {{review_link}}\n\n"
                            "आपके विश्वास और सहयोग के लिए धन्यवाद।\n"
                            "— {{agent_name}}"
                        )
                    },
                    {
                        'id': 'rev_hi_3',
                        'title': '🤝 पेशेवर सेवा फीडबैक',
                        'text': (
                            "नमस्ते, मैं आपके और आपके परिवार के लिए सर्वोत्तम बीमा सलाह देने के लिए सदैव तत्पर हूँ।\n\n"
                            "यदि आप मेरी सेवा से संतुष्ट हैं, तो कृपया एक समीक्षा अवश्य लिखें:\n"
                            "{{review_link}}\n\n"
                            "सस्नेह,\n"
                            "{{agent_name}}"
                        )
                    }
                ]
            },
            'gu': {
                'label': 'ગુજરાતી (Gujarati)',
                'templates': [
                    {
                        'id': 'rev_gu_1',
                        'title': '⭐ રિવ્યૂ અને રેટિંગ વિનંતી (ભલામણ કરેલ)',
                        'text': (
                            "નમસ્તે! તમારા ઇન્સ્યોરન્સ એડવાઇઝર તરીકે મારા પર વિશ્વાસ મૂકવા બદલ આભાર.\n\n"
                            "PadosiAgent પર મારી ઓફિશિયલ પ્રોફાઇલ પર ફક્ત 30 સેકન્ડ ફાળવીને તમારો કિંમતી રિવ્યૂ અને 5-સ્ટાર રેટિંગ આપવા વિનંતી છે:\n\n"
                            "⭐ અહીં રિવ્યૂ આપો:\n"
                            "{{review_link}}\n\n"
                            "તમારો સારો પ્રતિભાવ મને વધુ સારી સેવા આપવા પ્રોત્સાહિત કરશે!\n"
                            "— {{agent_name}}"
                        )
                    },
                    {
                        'id': 'rev_gu_2',
                        'title': '⚡ ઝડપી 5-સ્ટાર રેટિંગ',
                        'text': (
                            "નમસ્તે, તમારો અનુભવ મારા માટે ખૂબ મૂલ્યવાન છે!\n\n"
                            "કૃપા કરીને PadosiAgent પર મારી સેવાને રેટ કરો અને તમારો અનુભવ શેર કરો:\n"
                            "⭐ અત્યારે રેટ કરો: {{review_link}}\n\n"
                            "તમારા સહકાર અને વિશ્વાસ બદલ આભાર.\n"
                            "— {{agent_name}}"
                        )
                    },
                    {
                        'id': 'rev_gu_3',
                        'title': '🤝 વિશ્વાસુ સલાહકાર ફીડબેક',
                        'text': (
                            "નમસ્તે, હું તમારા અને તમારા પરિવાર માટે શ્રેષ્ઠ વીમા માર્ગદર્શન આપવા કટિબદ્ધ છું.\n\n"
                            "જો તમે મારી સેવાથી સંતુષ્ટ હોવ તો કૃપા કરીને PadosiAgent પર એક રિવ્યૂ ચોક્કસ આપશો:\n"
                            "{{review_link}}\n\n"
                            "આપનો સ્નેહી,\n"
                            "{{agent_name}}"
                        )
                    }
                ]
            },
            'mr': {
                'label': 'मराठी (Marathi)',
                'templates': [
                    {
                        'id': 'rev_mr_1',
                        'title': '⭐ रिव्ह्यू आणि रेटिंग विनंती',
                        'text': (
                            "नमस्कार! आपला विमा सल्लागार म्हणून माझ्यावर विश्वास ठेवल्याबद्दल धन्यवाद.\n\n"
                            "कृपया PadosiAgent वर माझ्या प्रोफाइलवर ३० सेकंद काढून आपला बहुमूल्य अभिप्राय आणि ५-स्टार रेटिंग द्या:\n\n"
                            "⭐ येथे रिव्ह्यू द्या:\n"
                            "{{review_link}}\n\n"
                            "— {{agent_name}}"
                        )
                    }
                ]
            }
        }
    },
    'social': {
        'label': 'Share on Social Media',
        'languages': {
            'en': {
                'label': 'English',
                'templates': [
                    {
                        'id': 'soc_en_1',
                        'title': '🚀 Referral Invite (Recommended)',
                        'text': (
                            "Hi, I'm {{agent_name}}, an Insurance Agent.\n\n"
                            "Join PadosiAgent and take your digital presence to the next level "
                            "with better online visibility, professional branding, and greater reach.\n\n"
                            "🚀 Build your digital identity and connect with more potential customers.\n\n"
                            "🔗 Join through my referral:\n"
                            "{{referral_link}}\n\n"
                            "Let's grow together with PadosiAgent!"
                        )
                    },
                    {
                        'id': 'soc_en_2',
                        'title': '🪪 Digital Business Card & Contact',
                        'text': (
                            "Hi! I'm {{agent_name}}, your neighbourhood insurance advisor.\n\n"
                            "Save my digital visiting card, explore insurance plans, and connect with me directly:\n\n"
                            "🪪 My Digital Visiting Card:\n"
                            "{{card_link}}\n\n"
                            "Feel free to reach out for any life, health, or motor insurance queries!"
                        )
                    },
                    {
                        'id': 'soc_en_3',
                        'title': '🛡️ Trusted Insurance Advisor',
                        'text': (
                            "Looking for trusted and personalized insurance guidance for your family?\n\n"
                            "I'm {{agent_name}}, verified Insurance Advisor on PadosiAgent.\n\n"
                            "Save my digital visiting card and connect with me here:\n"
                            "{{card_link}}\n\n"
                            "Always happy to help you protect what matters most!"
                        )
                    }
                ]
            },
            'hi': {
                'label': 'हिन्दी (Hindi)',
                'templates': [
                    {
                        'id': 'soc_hi_1',
                        'title': '🚀 रेफरल आमंत्रण (अनुशंसित)',
                        'text': (
                            "नमस्ते, मैं {{agent_name}}, एक इंश्योरेंस एजेंट हूँ।\n\n"
                            "PadosiAgent से जुड़ें और बेहतर ऑनलाइन विजिबिलिटी, प्रोफेशनल ब्रांडिंग "
                            "और अधिक पहुंच के साथ अपनी डिजिटल पहचान को अगले स्तर पर ले जाएं।\n\n"
                            "🚀 अपनी डिजिटल पहचान बनाएं और अधिक संभावित ग्राहकों से जुड़ें।\n\n"
                            "🔗 मेरे रेफरल से जुड़ें:\n"
                            "{{referral_link}}\n\n"
                            "आइए, PadosiAgent के साथ मिलकर आगे बढ़ें!"
                        )
                    },
                    {
                        'id': 'soc_hi_2',
                        'title': '🪪 डिजिटल विजिटिंग कार्ड',
                        'text': (
                            "नमस्ते! मैं {{agent_name}}, आपका विश्वसनीय इंश्योरेंस सलाहकार।\n\n"
                            "मेरा डिजिटल विजिटिंग कार्ड सेव करें और बीमा संबंधी सलाह के लिए संपर्क करें:\n\n"
                            "🪪 डिजिटल कार्ड:\n"
                            "{{card_link}}\n\n"
                            "लाइफ, हेल्थ और मोटर इंश्योरेंस के लिए कभी भी संपर्क करें!"
                        )
                    },
                    {
                        'id': 'soc_hi_3',
                        'title': '🛡️ विश्वसनीय बीमा सलाहकार',
                        'text': (
                            "क्या आप अपने परिवार के लिए सही बीमा योजना की तलाश में हैं?\n\n"
                            "मैं {{agent_name}}, PadosiAgent पर वेरिफाइड इंश्योरेंस एडवाइजर हूँ।\n\n"
                            "मेरा डिजिटल विजिटिंग कार्ड सेव करें:\n"
                            "{{card_link}}"
                        )
                    }
                ]
            },
            'gu': {
                'label': 'ગુજરાતી (Gujarati)',
                'templates': [
                    {
                        'id': 'soc_gu_1',
                        'title': '🚀 રેફરલ આમંત્રણ (ભલામણ કરેલ)',
                        'text': (
                            "નમસ્તે, હું {{agent_name}}, એક ઇન્સ્યોરન્સ એજન્ટ છું.\n\n"
                            "PadosiAgent સાથે જોડાઓ અને વધુ સારી ઓનલાઇન વિઝિબિલિટી, પ્રોફેશનલ બ્રાન્ડિંગ "
                            "અને વધુ પહોંચ સાથે તમારી ડિજિટલ હાજરીને આગળના સ્તરે લઈ જાઓ.\n\n"
                            "🚀 તમારી ડિજિટલ ઓળખ બનાવો અને વધુ સંભવિત ગ્રાહકો સાથે જોડાઓ.\n\n"
                            "🔗 મારા રેફરલથી જોડાઓ:\n"
                            "{{referral_link}}\n\n"
                            "ચાલો, PadosiAgent સાથે મળીને આગળ વધીએ!"
                        )
                    },
                    {
                        'id': 'soc_gu_2',
                        'title': '🪪 ડિજિટલ વિઝિટિંગ કાર્ડ',
                        'text': (
                            "નમસ્તે! હું {{agent_name}}, તમારો વિશ્વાસુ ઇન્સ્યોરન્સ એડવાઇઝર.\n\n"
                            "મારું ડિજિટલ વિઝિટિંગ કાર્ડ સેવ કરો અને વીમા સેવાઓ માટે મારો સીધો સંપર્ક કરો:\n\n"
                            "🪪 મારું ડિજિટલ કાર્ડ:\n"
                            "{{card_link}}\n\n"
                            "લાઇફ, હેલ્થ કે વાહન વીમાની માહિતી માટે આજે જ સંપર્ક કરો!"
                        )
                    },
                    {
                        'id': 'soc_gu_3',
                        'title': '🛡️ વિશ્વાસુ ઇન્સ્યોરન્સ એડવાઇઝર',
                        'text': (
                            "તમારા અને તમારા પરિવાર માટે શ્રેષ્ઠ વીમા આયોજન શોધી રહ્યા છો?\n\n"
                            "હું {{agent_name}}, PadosiAgent પર વેરિફાઇડ ઇન્સ્યોરન્સ એડવાઇઝર છું.\n\n"
                            "મારું ડિજિટલ વિઝિટિંગ કાર્ડ સેવ કરો:\n"
                            "{{card_link}}"
                        )
                    }
                ]
            },
            'mr': {
                'label': 'मराठी (Marathi)',
                'templates': [
                    {
                        'id': 'soc_mr_1',
                        'title': '🚀 रेफरल आमंत्रण',
                        'text': (
                            "नमस्कार, मी {{agent_name}}, एक विमा एजंट.\n\n"
                            "PadosiAgent सोबत जोडा आणि अधिक चांगली ऑनलाइन व्हिजिबिलिटी, प्रोफेशनल ब्रँडिंग "
                            "आणि अधिक पोहोच यासह तुमची डिजिटल ओळख पुढच्या पातळीवर न्या.\n\n"
                            "🚀 तुमची डिजिटल ओळख तयार करा आणि अधिक संभाव्य ग्राहकांशी जोडा.\n\n"
                            "🔗 माझ्या रेफरलमधून जॉइन करा:\n"
                            "{{referral_link}}\n\n"
                            "चला, PadosiAgent सोबत एकत्र वाढूया!"
                        )
                    }
                ]
            }
        }
    }
}


# Full product language set (matches agent registration LANGUAGE_OPTIONS)
STUDIO_LANGUAGE_ORDER = (
    ('en', 'English'),
    ('hi', 'Hindi'),
    ('gu', 'Gujarati'),
    ('mr', 'Marathi'),
    ('ta', 'Tamil'),
    ('te', 'Telugu'),
    ('kn', 'Kannada'),
    ('bn', 'Bengali'),
    ('pa', 'Punjabi'),
    ('ml', 'Malayalam'),
    ('or', 'Odia'),
    ('ur', 'Urdu'),
    ('as', 'Assamese'),
    ('raj', 'Rajasthani'),
)

# Compact default copy for languages beyond the hand-authored en/hi/gu/mr packs.
# review = Review & Rating default, refer = Refer tab, card = Social Media Share default
_ADDITIONAL_LANG_COPY = {
    'ta': {
        'label': 'Tamil',
        'review': (
            "வணக்கம்! உங்கள் காப்பீட்டு ஆலோசகராக என்னை நம்பியதற்கு நன்றி.\n\n"
            "PadosiAgent-இல் எனது சேவைக்கு 5-நட்சத்திர மதிப்பீடும் கருத்தும் தர 30 வினாடி ஒதுக்குங்கள்:\n\n"
            "⭐ இங்கே மதிப்பிடுங்கள்:\n{{review_link}}\n\n"
            "— {{agent_name}}"
        ),
        'refer': (
            "வணக்கம், நான் {{agent_name}}, காப்பீட்டு முகவர்.\n\n"
            "PadosiAgent மூலம் உங்கள் டிஜிட்டல் இருப்பை வளர்த்து அதிக வாடிக்கையாளர்களை அடையுங்கள்.\n\n"
            "🔗 என் பரிந்துரை இணைப்பு:\n{{referral_link}}\n\n"
            "PadosiAgent உடன் சேர்ந்து வளர்வோம்!"
        ),
        'card': (
            "வணக்கம்! நான் {{agent_name}}, உங்கள் பகுதி காப்பீட்டு ஆலோசகர்.\n\n"
            "🪪 என் டிஜிட்டல் விசிட்டிங் கார்டு:\n{{card_link}}\n\n"
            "ஆயுள், சுகாதாரம் அல்லது வாகன காப்பீடு குறித்து தொடர்பு கொள்ளுங்கள்!"
        ),
    },
    'te': {
        'label': 'Telugu',
        'review': (
            "నమస్కారం! మీ ఇన్సూరెన్స్ సలహాదారుగా నన్ను నమ్మినందుకు ధన్యవాదాలు.\n\n"
            "దయచేసి PadosiAgentలో నా సేవకు 5-స్టార్ రేటింగ్ మరియు రివ్యూ ఇవ్వండి:\n\n"
            "⭐ ఇక్కడ రేట్ చేయండి:\n{{review_link}}\n\n"
            "— {{agent_name}}"
        ),
        'refer': (
            "నమస్కారం, నేను {{agent_name}}, ఇన్సూరెన్స్ ఏజెంట్.\n\n"
            "PadosiAgentతో మీ డిజిటల్ ఉనికిని పెంచుకుని ఎక్కువ మంది కస్టమర్లను చేరుకోండి.\n\n"
            "🔗 నా రెఫరల్ లింక్:\n{{referral_link}}\n\n"
            "PadosiAgentతో కలిసి ఎదుగుదాం!"
        ),
        'card': (
            "నమస్కారం! నేను {{agent_name}}, మీ సమీప ఇన్సూరెన్స్ సలహాదారు.\n\n"
            "🪪 నా డిజిటల్ విజిటింగ్ కార్డ్:\n{{card_link}}\n\n"
            "లైఫ్, హెల్త్ లేదా మోటార్ ఇన్సూరెన్స్ కోసం సంప్రదించండి!"
        ),
    },
    'kn': {
        'label': 'Kannada',
        'review': (
            "ನಮಸ್ಕಾರ! ನಿಮ್ಮ ವಿಮಾ ಸಲಹೆಗಾರನಾಗಿ ನನ್ನನ್ನು ನಂಬಿದ್ದಕ್ಕೆ ಧನ್ಯವಾದಗಳು.\n\n"
            "ದಯವಿಟ್ಟು PadosiAgentನಲ್ಲಿ ನನ್ನ ಸೇವೆಗೆ 5-ಸ್ಟಾರ್ ರೇಟಿಂಗ್ ಮತ್ತು ವಿಮರ್ಶೆ ನೀಡಿ:\n\n"
            "⭐ ಇಲ್ಲಿ ರೇಟ್ ಮಾಡಿ:\n{{review_link}}\n\n"
            "— {{agent_name}}"
        ),
        'refer': (
            "ನಮಸ್ಕಾರ, ನಾನು {{agent_name}}, ವಿಮಾ ಏಜೆಂಟ್.\n\n"
            "PadosiAgent ಜೊತೆ ನಿಮ್ಮ ಡಿಜಿಟಲ್ ಹಾಜರಿ ಹೆಚ್ಚಿಸಿ ಹೆಚ್ಚು ಗ್ರಾಹಕರನ್ನು ತಲುಪಿ.\n\n"
            "🔗 ನನ್ನ ರೆಫರಲ್ ಲಿಂಕ್:\n{{referral_link}}\n\n"
            "PadosiAgent ಜೊತೆ ಬೆಳೆಯೋಣ!"
        ),
        'card': (
            "ನಮಸ್ಕಾರ! ನಾನು {{agent_name}}, ನಿಮ್ಮ ನೆರೆಹೊರೆಯ ವಿಮಾ ಸಲಹೆಗಾರ.\n\n"
            "🪪 ನನ್ನ ಡಿಜಿಟಲ್ ವಿಜಿಟಿಂಗ್ ಕಾರ್ಡ್:\n{{card_link}}\n\n"
            "ಲೈಫ್, ಹೆಲ್ತ್ ಅಥವಾ ಮೋಟಾರ್ ವಿಮೆಗಾಗಿ ಸಂಪರ್ಕಿಸಿ!"
        ),
    },
    'bn': {
        'label': 'Bengali',
        'review': (
            "নমস্কার! আপনার ইনস্যুরেন্স উপদেষ্টা হিসেবে আমাকে বিশ্বাস করার জন্য ধন্যবাদ।\n\n"
            "অনুগ্রহ করে PadosiAgent-এ আমার সেবায় ৫-স্টার রেটিং ও রিভিউ দিন:\n\n"
            "⭐ এখানে রেট করুন:\n{{review_link}}\n\n"
            "— {{agent_name}}"
        ),
        'refer': (
            "নমস্কার, আমি {{agent_name}}, ইনস্যুরেন্স এজেন্ট।\n\n"
            "PadosiAgent-এর সাথে আপনার ডিজিটাল উপস্থিতি বাড়ান এবং আরও গ্রাহকের কাছে পৌঁছান।\n\n"
            "🔗 আমার রেফারেল লিঙ্ক:\n{{referral_link}}\n\n"
            "PadosiAgent-এর সাথে একসাথে এগোই!"
        ),
        'card': (
            "নমস্কার! আমি {{agent_name}}, আপনার এলাকার ইনস্যুরেন্স উপদেষ্টা।\n\n"
            "🪪 আমার ডিজিটাল ভিজিটিং কার্ড:\n{{card_link}}\n\n"
            "লাইফ, হেলথ বা মোটর ইনস্যুরেন্সের জন্য যোগাযোগ করুন!"
        ),
    },
    'pa': {
        'label': 'Punjabi',
        'review': (
            "ਸਤ ਸ੍ਰੀ ਅਕਾਲ! ਤੁਹਾਡੇ ਬੀਮਾ ਸਲਾਹਕਾਰ ਵਜੋਂ ਮੇਰੇ ਉੱਤੇ ਭਰੋਸਾ ਕਰਨ ਲਈ ਧੰਨਵਾਦ।\n\n"
            "ਕਿਰਪਾ ਕਰਕੇ PadosiAgent ਉੱਤੇ ਮੇਰੀ ਸੇਵਾ ਨੂੰ 5-ਸਟਾਰ ਰੇਟਿੰਗ ਅਤੇ ਰਿਵਿਊ ਦਿਓ:\n\n"
            "⭐ ਇੱਥੇ ਰੇਟ ਕਰੋ:\n{{review_link}}\n\n"
            "— {{agent_name}}"
        ),
        'refer': (
            "ਸਤ ਸ੍ਰੀ ਅਕਾਲ, ਮੈਂ {{agent_name}}, ਇੰਸ਼ੋਰੈਂਸ ਏਜੰਟ ਹਾਂ।\n\n"
            "PadosiAgent ਨਾਲ ਆਪਣੀ ਡਿਜੀਟਲ ਮੌਜੂਦਗੀ ਵਧਾਓ ਅਤੇ ਹੋਰ ਗਾਹਕਾਂ ਤੱਕ ਪਹੁੰਚੋ।\n\n"
            "🔗 ਮੇਰਾ ਰੈਫਰਲ ਲਿੰਕ:\n{{referral_link}}\n\n"
            "PadosiAgent ਨਾਲ ਰਲ ਕੇ ਅੱਗੇ ਵਧੀਏ!"
        ),
        'card': (
            "ਸਤ ਸ੍ਰੀ ਅਕਾਲ! ਮੈਂ {{agent_name}}, ਤੁਹਾਡਾ ਨਜ਼ਦੀਕੀ ਬੀਮਾ ਸਲਾਹਕਾਰ ਹਾਂ।\n\n"
            "🪪 ਮੇਰਾ ਡਿਜੀਟਲ ਵਿਜ਼ਿਟਿੰਗ ਕਾਰਡ:\n{{card_link}}\n\n"
            "ਲਾਈਫ, ਹੈਲਥ ਜਾਂ ਮੋਟਰ ਬੀਮੇ ਲਈ ਸੰਪਰਕ ਕਰੋ!"
        ),
    },
    'ml': {
        'label': 'Malayalam',
        'review': (
            "നമസ്കാരം! നിങ്ങളുടെ ഇൻഷുറൻസ് ഉപദേഷ്ടാവായി എന്നെ വിശ്വസിച്ചതിന് നന്ദി.\n\n"
            "ദയവായി PadosiAgent-ൽ എന്റെ സേവനത്തിന് 5-സ്റ്റാർ റേറ്റിംഗും റിവ്യൂവും നൽകൂ:\n\n"
            "⭐ ഇവിടെ റേറ്റ് ചെയ്യൂ:\n{{review_link}}\n\n"
            "— {{agent_name}}"
        ),
        'refer': (
            "നമസ്കാരം, ഞാൻ {{agent_name}}, ഇൻഷുറൻസ് ഏജന്റ്.\n\n"
            "PadosiAgent ഉപയോഗിച്ച് നിങ്ങളുടെ ഡിജിറ്റൽ സാന്നിധ്യം വളർത്തി കൂടുതൽ ഉപഭോക്താക്കളിലേക്ക് എത്തൂ.\n\n"
            "🔗 എന്റെ റഫറൽ ലിങ്ക്:\n{{referral_link}}\n\n"
            "PadosiAgent-നൊപ്പം വളരാം!"
        ),
        'card': (
            "നമസ്കാരം! ഞാൻ {{agent_name}}, നിങ്ങളുടെ പ്രദേശത്തെ ഇൻഷുറൻസ് ഉപദേഷ്ടാവ്.\n\n"
            "🪪 എന്റെ ഡിജിറ്റൽ വിസിറ്റിംഗ് കാർഡ്:\n{{card_link}}\n\n"
            "ലൈഫ്, ഹെൽത്ത് അല്ലെങ്കിൽ മോട്ടോർ ഇൻഷുറൻസിന് ബന്ധപ്പെടൂ!"
        ),
    },
    'or': {
        'label': 'Odia',
        'review': (
            "ନମସ୍କାର! ଆପଣଙ୍କ ବୀମା ପରାମର୍ଶଦାତା ଭାବରେ ମୋତେ ବିଶ୍ୱାସ କରିଥିବାରୁ ଧନ୍ୟବାଦ।\n\n"
            "ଦୟାକରି PadosiAgentରେ ମୋ ସେବାକୁ 5-ଷ୍ଟାର ରେଟିଙ୍ଗ ଓ ରିଭ୍ୟୁ ଦିଅନ୍ତୁ:\n\n"
            "⭐ ଏଠାରେ ରେଟ୍ କରନ୍ତୁ:\n{{review_link}}\n\n"
            "— {{agent_name}}"
        ),
        'refer': (
            "ନମସ୍କାର, ମୁଁ {{agent_name}}, ଇନ୍‌ସ୍ୟୋରେନ୍ସ ଏଜେଣ୍ଟ।\n\n"
            "PadosiAgent ସହିତ ଆପଣଙ୍କ ଡିଜିଟାଲ୍ ଉପସ୍ଥିତି ବଢ଼ାନ୍ତୁ ଏବଂ ଅଧିକ ଗ୍ରାହକଙ୍କ ପାଖରେ ପହଞ୍ଚନ୍ତୁ।\n\n"
            "🔗 ମୋ ରେଫରାଲ୍ ଲିଙ୍କ୍:\n{{referral_link}}\n\n"
            "PadosiAgent ସହିତ ଏକାଠି ଆଗକୁ ବଢ଼ିବା!"
        ),
        'card': (
            "ନମସ୍କାର! ମୁଁ {{agent_name}}, ଆପଣଙ୍କ ଅଞ୍ଚଳର ବୀମା ପରାମର୍ଶଦାତା।\n\n"
            "🪪 ମୋ ଡିଜିଟାଲ୍ ଭିଜିଟିଙ୍ଗ୍ କାର୍ଡ:\n{{card_link}}\n\n"
            "ଲାଇଫ୍, ହେଲ୍ଥ୍ କିମ୍ବା ମୋଟର ବୀମା ପାଇଁ ଯୋଗାଯୋଗ କରନ୍ତୁ!"
        ),
    },
    'ur': {
        'label': 'Urdu',
        'review': (
            "السلام علیکم! اپنے انشورنس مشیر کے طور پر مجھ پر اعتماد کرنے کا شکریہ۔\n\n"
            "براہ کرم PadosiAgent پر میری سروس کو 5-ستارہ ریٹنگ اور ریویو دیں:\n\n"
            "⭐ یہاں ریٹ کریں:\n{{review_link}}\n\n"
            "— {{agent_name}}"
        ),
        'refer': (
            "السلام علیکم، میں {{agent_name}}، انشورنس ایجنٹ ہوں۔\n\n"
            "PadosiAgent کے ساتھ اپنی ڈیجیٹل موجودگی بڑھائیں اور زیادہ کلائنٹس تک پہنچیں۔\n\n"
            "🔗 میرا ریفرل لنک:\n{{referral_link}}\n\n"
            "PadosiAgent کے ساتھ مل کر آگے بڑھیں!"
        ),
        'card': (
            "السلام علیکم! میں {{agent_name}}، آپ کا قریبی انشورنس مشیر ہوں۔\n\n"
            "🪪 میرا ڈیجیٹل وزٹنگ کارڈ:\n{{card_link}}\n\n"
            "لائف، ہیلتھ یا موٹر انشورنس کے لیے رابطہ کریں!"
        ),
    },
    'as': {
        'label': 'Assamese',
        'review': (
            "নমস্কাৰ! আপোনাৰ বীমা পৰামৰ্শদাতা হিচাপে মোক বিশ্বাস কৰাৰ বাবে ধন্যবাদ।\n\n"
            "অনুগ্ৰহ কৰি PadosiAgentত মোৰ সেৱাক 5-ষ্টাৰ ৰেটিং আৰু ৰিভিউ দিয়ক:\n\n"
            "⭐ ইয়াত ৰেট কৰক:\n{{review_link}}\n\n"
            "— {{agent_name}}"
        ),
        'refer': (
            "নমস্কাৰ, মই {{agent_name}}, ইনছ্যুৰেন্স এজেণ্ট।\n\n"
            "PadosiAgentৰ সৈতে আপোনাৰ ডিজিটেল উপস্থিতি বৃদ্ধি কৰক আৰু অধিক গ্ৰাহকলৈ প্ৰসাৰিত হওক।\n\n"
            "🔗 মোৰ ৰেফাৰেল লিংক:\n{{referral_link}}\n\n"
            "PadosiAgentৰ সৈতে একেলগে আগবাঢ়োঁ!"
        ),
        'card': (
            "নমস্কাৰ! মই {{agent_name}}, আপোনাৰ অঞ্চলৰ বীমা পৰামৰ্শদাতা।\n\n"
            "🪪 মোৰ ডিজিটেল ভিজিটিং কাৰ্ড:\n{{card_link}}\n\n"
            "লাইফ, হেল্থ বা মটৰ বীমাৰ বাবে যোগাযোগ কৰক!"
        ),
    },
    'raj': {
        'label': 'Rajasthani',
        'review': (
            "राम राम! थारा बीमा सलाहकार रूप में म्हारे ऊपर भरोसो करबा रो धन्यवाद।\n\n"
            "कृपया PadosiAgent पर म्हारी सेवा ने 5-स्टार रेटिंग अर रिव्यू दो:\n\n"
            "⭐ अठे रेट करो:\n{{review_link}}\n\n"
            "— {{agent_name}}"
        ),
        'refer': (
            "राम राम, म्हैं {{agent_name}}, इंश्योरेंस एजेंट हूं।\n\n"
            "PadosiAgent रे साथै थारी डिजिटल पहचान बढ़ाओ अर ज्यादा ग्राहकां तांई पहुंचो।\n\n"
            "🔗 म्हारो रेफरल लिंक:\n{{referral_link}}\n\n"
            "PadosiAgent रे साथै मिलकर आगे बढ़ां!"
        ),
        'card': (
            "राम राम! म्हैं {{agent_name}}, थारा इलाके रो बीमा सलाहकार हूं।\n\n"
            "🪪 म्हारो डिजिटल विजिटिंग कार्ड:\n{{card_link}}\n\n"
            "लाइफ, हेल्थ या मोटर बीमा खातिर संपर्क करो!"
        ),
    },
}


def _lang_pack(code, label, review_text, refer_text, card_text):
    return {
        'review': {
            'label': label,
            'templates': [{
                'id': f'rev_{code}_1',
                'title': '⭐ Review Request',
                'text': review_text,
            }],
        },
        'social': {
            'label': label,
            'templates': [
                {
                    'id': f'soc_{code}_1',
                    'title': '🚀 Referral Invite',
                    'text': refer_text,
                },
                {
                    'id': f'soc_{code}_2',
                    'title': '🪪 Digital Visiting Card',
                    'text': card_text,
                },
            ],
        },
    }


def _merge_all_studio_languages(templates):
    """Ensure every product language exists in review/social template packs."""
    if not isinstance(templates, dict):
        return templates
    for code, label in STUDIO_LANGUAGE_ORDER:
        extra = _ADDITIONAL_LANG_COPY.get(code)
        # Prefer already-authored packs (en/hi/gu/mr). Fill gaps from extras.
        for mode in ('review', 'social'):
            mode_obj = templates.setdefault(mode, {'label': mode.title(), 'languages': {}})
            langs = mode_obj.setdefault('languages', {})
            if code in langs and isinstance(langs[code], dict) and langs[code].get('templates'):
                # Ensure social has a card template for Social Media Share tab
                if mode == 'social' and extra and len(langs[code].get('templates') or []) < 2:
                    langs[code]['templates'].append({
                        'id': f'soc_{code}_2',
                        'title': '🪪 Digital Visiting Card',
                        'text': extra['card'],
                    })
                continue
            if not extra:
                continue
            pack = _lang_pack(code, extra.get('label') or label, extra['review'], extra['refer'], extra['card'])
            langs[code] = pack[mode]
    return templates


_merge_all_studio_languages(STUDIO_TEMPLATES)

_SOCIAL_INVITE_IDS = tuple(f'soc_{code}_1' for code, _ in STUDIO_LANGUAGE_ORDER)


def get_studio_language_options(templates=None):
    """Ordered language list for the Invite Studio dropdown."""
    templates = templates or STUDIO_TEMPLATES
    review_langs = ((templates.get('review') or {}).get('languages') or {})
    social_langs = ((templates.get('social') or {}).get('languages') or {})
    options = []
    seen = set()
    for code, fallback_label in STUDIO_LANGUAGE_ORDER:
        lang = review_langs.get(code) or social_langs.get(code)
        if not lang:
            continue
        options.append({
            'code': code,
            'label': lang.get('label') or fallback_label,
        })
        seen.add(code)
    # Include any unexpected saved languages at the end
    for code, lang in {**social_langs, **review_langs}.items():
        if code in seen or not isinstance(lang, dict):
            continue
        options.append({'code': code, 'label': lang.get('label') or code})
    return options


def _price_free_social_invites():
    by_id = {}
    by_lang = {}
    for code, lang in STUDIO_TEMPLATES['social']['languages'].items():
        for tmpl in lang.get('templates') or []:
            if tmpl.get('id') in _SOCIAL_INVITE_IDS:
                by_id[tmpl['id']] = tmpl
                by_lang[code] = tmpl
                break
    return by_id, by_lang


def _template_lists_plan_price(text):
    if not text:
        return False
    lowered = str(text).lower()
    return (
        '₹' in text
        or '{{digital_price}}' in text
        or '{{professional_price}}' in text
        or 'campaign offer' in lowered
        or 'current campaign' in lowered
    )


def strip_saved_campaign_prices(templates):
    """
    A saved Invite Studio copy can still print plan prices.
    Replace that referral invite with the built-in price-free message.
    """
    if not isinstance(templates, dict):
        return templates
    social = templates.get('social')
    if not isinstance(social, dict):
        return templates
    by_id, by_lang = _price_free_social_invites()
    for code, lang in (social.get('languages') or {}).items():
        if not isinstance(lang, dict):
            continue
        source = by_lang.get(code) or by_lang.get('en')
        if not source:
            continue
        items = [tmpl for tmpl in (lang.get('templates') or []) if isinstance(tmpl, dict)]
        priced = [
            tmpl for tmpl in items
            if tmpl.get('id') in by_id or _template_lists_plan_price(tmpl.get('text'))
        ]
        # Only the recommended invite should change. Leave visiting-card messages alone.
        target = next((tmpl for tmpl in priced if tmpl.get('id') in by_id), None)
        if target is None:
            target = next((tmpl for tmpl in priced if _template_lists_plan_price(tmpl.get('text'))), None)
        if target is None or not _template_lists_plan_price(target.get('text')):
            continue
        target['title'] = source['title']
        target['text'] = source['text']
    return templates


def strip_profile_link_from_text(text):
    """Remove profile URL placeholders and their label lines from invite copy."""
    if not text:
        return text
    lines = str(text).split('\n')
    cleaned = []
    i = 0
    while i < len(lines):
        line = lines[i]
        nxt = lines[i + 1] if i + 1 < len(lines) else ''
        # Drop label + next line when next line is the profile placeholder/URL
        if (
            _PROFILE_LABEL_RE.search(line)
            and (
                '{{profile_link}}' in nxt
                or '/gj/' in nxt
                or 'padosiagent.com' in nxt.lower()
            )
        ):
            i += 2
            continue
        if '{{profile_link}}' in line:
            i += 1
            continue
        cleaned.append(line)
        i += 1
    text = '\n'.join(cleaned)
    text = re.sub(r'\n{3,}', '\n\n', text).strip()
    return text


def strip_profile_links_from_templates(templates):
    """Ensure saved/admin Invite Studio templates never include profile links."""
    if not isinstance(templates, dict):
        return templates
    for mode in templates.values():
        if not isinstance(mode, dict):
            continue
        for lang in (mode.get('languages') or {}).values():
            if not isinstance(lang, dict):
                continue
            for tmpl in (lang.get('templates') or []):
                if isinstance(tmpl, dict) and tmpl.get('text'):
                    tmpl['text'] = strip_profile_link_from_text(tmpl['text'])
    return templates


def get_invite_studio_config():
    """
    Fetches the dynamic Invite & Share Studio config from SiteSetting DB table.
    Falls back to STUDIO_TEMPLATES default dictionary if not set.
    """
    from apps.home.models.site_setting import SiteSetting
    default_config = {
        'modal_title': 'PadosiAgent Invite & Share Studio',
        'modal_subtitle': 'Send pre-drafted or customized invites to collect 5-star client reviews or share your digital presence across social networks.',
        'tab_review_label': 'Review & Rating',
        'tab_social_label': 'Social Media Share',
        'digital_price': '999',
        'professional_price': '4999',
        'templates': STUDIO_TEMPLATES,
    }
    config = SiteSetting.get_value('invite_studio_config', default_config)
    if isinstance(config, str):
        try:
            config = json.loads(config)
        except Exception:
            config = default_config
    if not isinstance(config, dict):
        config = default_config

    for k, v in default_config.items():
        if k not in config or config[k] is None or config[k] == '':
            config[k] = v
    strip_saved_campaign_prices(config.get('templates'))
    # Saved admin JSON may only contain the old 4 languages — always fill the rest
    _merge_all_studio_languages(config.get('templates'))
    strip_profile_links_from_templates(config.get('templates'))
    return config


def render_template_text(raw_text, agent_name, profile_link, review_link, card_link, referral_link, digital_price="999", professional_price="4999"):
    """
    Replaces template variables with real agent values.
    Profile links are intentionally stripped from invite messages.
    """
    if not raw_text:
        return ""
    text = strip_profile_link_from_text(str(raw_text))
    return (
        text
        .replace("{{agent_name}}", agent_name or "Insurance Advisor")
        .replace("{{profile_link}}", "")  # never inject profile URLs into invite copy
        .replace("{{review_link}}", review_link or "")
        .replace("{{card_link}}", card_link or "")
        .replace("{{referral_link}}", referral_link or "")
        .replace("{{digital_price}}", str(digital_price))
        .replace("{{professional_price}}", str(professional_price))
    )


def get_studio_context(request, agent, profile=None, champ_participant=None):
    """
    Builds all context variables needed for the WhatsApp & Social Invite Studio.
    Integrates dynamic admin configuration from SiteSetting.
    """
    config = get_invite_studio_config()
    templates = config.get('templates') or STUDIO_TEMPLATES
    dig_price = str(config.get('digital_price', '999'))
    prof_price = str(config.get('professional_price', '4999'))

    slug = (profile.slug if profile and profile.slug else '') or getattr(agent, 'agent_slug', '') or str(agent.id)
    state_code = agent.state_code() if callable(getattr(agent, 'state_code', None)) else getattr(agent, 'state_code', 'gj')
    
    # Profile link
    if slug:
        profile_url = request.build_absolute_uri(
            reverse('agents:agent_public_profile_state_direct', kwargs={'state_code': state_code, 'slug': slug})
        )
    else:
        profile_url = request.build_absolute_uri('/')

    # Review link
    if slug:
        review_url = request.build_absolute_uri(
            reverse('agents:agent_public_review', kwargs={'slug': slug})
        )
    else:
        review_url = profile_url

    # Card link
    if slug:
        card_url = request.build_absolute_uri(
            reverse('agents:agent_public_card', kwargs={'slug': slug})
        )
    else:
        card_url = profile_url

    # Referral link
    domain = request.get_host()
    scheme = 'https' if request.is_secure() else 'http'
    if champ_participant and getattr(champ_participant, 'referral_id', None):
        referral_url = f"{scheme}://{domain}/agent-registration/join/{champ_participant.referral_id}/"
    else:
        ref_id = getattr(agent, 'referral_id', None) or slug
        referral_url = f"{scheme}://{domain}/agent-registration/join/{ref_id}/"

    agent_name = (profile.display_name if profile and profile.display_name else '') or agent.fullname or 'Insurance Agent'

    # Initial template text resolution
    rev_tpl_text = ''
    try:
        rev_tpl_text = templates['review']['languages']['en']['templates'][0]['text']
    except Exception:
        rev_tpl_text = STUDIO_TEMPLATES['review']['languages']['en']['templates'][0]['text']

    soc_tpl_text = ''
    try:
        soc_tpl_text = templates['social']['languages']['en']['templates'][0]['text']
    except Exception:
        soc_tpl_text = STUDIO_TEMPLATES['social']['languages']['en']['templates'][0]['text']

    default_review_text = render_template_text(
        rev_tpl_text,
        agent_name=agent_name,
        profile_link=profile_url,
        review_link=review_url,
        card_link=card_url,
        referral_link=referral_url,
        digital_price=dig_price,
        professional_price=prof_price,
    )

    default_social_text = render_template_text(
        soc_tpl_text,
        agent_name=agent_name,
        profile_link=profile_url,
        review_link=review_url,
        card_link=card_url,
        referral_link=referral_url,
        digital_price=dig_price,
        professional_price=prof_price,
    )

    return {
        'studio_config': config,
        'studio_templates_json': json.dumps(templates, ensure_ascii=False),
        'studio_languages': get_studio_language_options(templates),
        'studio_modal_title': config.get('modal_title', 'PadosiAgent Invite & Share Studio'),
        'studio_modal_subtitle': config.get('modal_subtitle', 'Send pre-drafted or customized invites to collect 5-star client reviews or share your digital presence across social networks.'),
        'studio_tab_review_label': config.get('tab_review_label', 'Review & Rating'),
        'studio_tab_social_label': config.get('tab_social_label', 'Social Media Share'),
        'studio_profile_url': profile_url,
        'studio_review_url': review_url,
        'studio_card_url': card_url,
        'studio_referral_url': referral_url,
        'studio_agent_name': agent_name,
        'studio_dig_price': dig_price,
        'studio_prof_price': prof_price,
        'studio_default_review_text': default_review_text,
        'studio_default_social_text': default_social_text,
        'studio_default_review_encoded': quote(default_review_text),
        'studio_default_social_encoded': quote(default_social_text),
    }
