from urllib.parse import quote

# 9 Supported Languages with 5 tailored templates each
WHATSAPP_TEMPLATES = {
    'en': {
        'label': 'English',
        'templates': [
            {
                'id': 'en_1',
                'title': 'Referral invite (recommended)',
                'text': "Hi, I'm {{agent_name}}, an Insurance Agent. 👋\n\nI'm growing my digital presence with PadosiAgent and would love to have you join the platform too.\n\nJoin PadosiAgent through my referral link and take your insurance business online 🚀\n\n👉 {{referral_link}}"
            },
            {
                'id': 'en_2',
                'title': '50% Limited Campaign Offer',
                'text': "Special invite from {{agent_name}}!\n\nPadosiAgent is hosting the National Referral Championship. Unlock 50% OFF today on your verified digital profile.\n\nClaim offer here:\n{{referral_link}}"
            },
            {
                'id': 'en_3',
                'title': 'Grow Your Insurance Business Online',
                'text': "Fellow Advisor, take your insurance career digital with PadosiAgent. Verified badge, reviews & leads all in one place.\n\nRegister with my invite code: {{referral_link}}\nSee how my profile looks: {{profile_link}}"
            },
            {
                'id': 'en_4',
                'title': 'New Customer Visibility',
                'text': "Want customers in your area to discover you easily? Get listed on India's top insurance advisor network at just ₹{{digital_price}}/year!\n\nUse my invitation link: {{referral_link}}"
            },
            {
                'id': 'en_5',
                'title': 'Direct Recommendation',
                'text': "I personally recommend PadosiAgent for all licensed insurance agents. Check it out and unlock exclusive campaign pricing:\n{{referral_link}}"
            }
        ]
    },
    'hi': {
        'label': 'हिन्दी (Hindi)',
        'templates': [
            {
                'id': 'hi_1',
                'title': 'रेफरल निमंत्रण (अनुशंसित)',
                'text': "नमस्ते, मैं {{agent_name}}, एक इंश्योरेंस एजेंट हूँ। 👋\n\nमैं PadosiAgent के साथ अपनी डिजिटल पहचान बढ़ा रहा हूँ और चाहूँगा कि आप भी इस प्लेटफॉर्म से जुड़ें।\n\nअपने इंश्योरेंस व्यवसाय को ऑनलाइन ले जाने के लिए मेरे रेफरल लिंक से PadosiAgent पर जुड़ें 🚀\n\n👉 {{referral_link}}"
            },
            {
                'id': 'hi_2',
                'title': '50% छूट का विशेष अवसर',
                'text': "साथी एजेंट, PadosiAgent नेशनल चैंपियनशिप के तहत अभी 50% की विशेष छूट मिल रही है।\n\nतुरंत लाभ उठाएं और डिजिटल एडवाइजर बनें:\n{{referral_link}}"
            },
            {
                'id': 'hi_3',
                'title': 'विश्वसनीयता और रिव्यूज',
                'text': "ग्राहकों का विश्वास जीतें और अपना इंश्योरेंस बिजनेस ऑनलाइन बढ़ाएं। PadosiAgent पर आज ही रजिस्टर करें:\n{{referral_link}}"
            },
            {
                'id': 'hi_4',
                'title': 'वेरिफाइड एजेंट बैज',
                'text': "अपने शहर में वेरिफाइड एजेंट की पहचान बनाएं। मात्र ₹{{digital_price}}/वर्ष में शुरू करें:\n{{referral_link}}"
            },
            {
                'id': 'hi_5',
                'title': 'सीधा निमंत्रण',
                'text': "मैंने PadosiAgent जॉइन किया है और रिस्पॉन्स बहुत बढ़िया है। आप भी जुड़ें:\n{{referral_link}}"
            }
        ]
    },
    'gu': {
        'label': 'ગુજરાતી (Gujarati)',
        'templates': [
            {
                'id': 'gu_1',
                'title': 'રેફરલ આમંત્રણ (ભલામણ)',
                'text': "નમસ્તે, હું {{agent_name}}, ઇન્સ્યોરન્સ એજન્ટ છું. 👋\n\nહું PadosiAgent સાથે મારી ડિજિટલ હાજરી વધારી રહ્યો છું અને તમે પણ પ્લેટફોર્મમાં જોડાઓ તે મારી ઈચ્છા છે.\n\nતમારા વીમા વ્યવસાયને ઓનલાઇન લાવવા મારા રેફરલ લિંકથી PadosiAgent માં જોડાઓ 🚀\n\n👉 {{referral_link}}"
            },
            {
                'id': 'gu_2',
                'title': '૫૦% ડિસ્કાઉન્ટ ઓફર',
                'text': "વિશેષ ઓફર! PadosiAgent નેશનલ ચેમ્પિયનશિપ હેઠળ 50% ડિસ્કાઉન્ટ મેળવો:\n{{referral_link}}"
            },
            {
                'id': 'gu_3',
                'title': 'ઓનલાઇન બિઝનેસ ગ્રોથ',
                'text': "તમારા વીમા વ્યવસાયને ઓનલાઇન લઈ જાઓ. વેરિફાઇડ બેજ અને રિવ્યુઝ સાથે ગ્રાહકોનો વિશ્વાસ જીતો:\n{{referral_link}}"
            },
            {
                'id': 'gu_4',
                'title': 'ગ્રાહકોની શોધમાં આગળ રહો',
                'text': "તમારા વિસ્તારમાં ગ્રાહકો તમને સરળતાથી શોધી શકે તે માટે આજે જ લિસ્ટ થાઓ:\n{{referral_link}}"
            },
            {
                'id': 'gu_5',
                'title': 'ખાસ ભલામણ',
                'text': "હું પોતે PadosiAgent વાપરું છું. તમે પણ જોડાઈને ફાયદો ઉઠાવો:\n{{referral_link}}"
            }
        ]
    },
    'mr': {
        'label': 'मराठी (Marathi)',
        'templates': [
            {
                'id': 'mr_1',
                'title': 'रेफरल निमंत्रण (शिफारस)',
                'text': "नमस्कार, मी {{agent_name}}, विमा सल्लागार आहे. 👋\n\nमी PadosiAgent सोबत माझी डिजिटल ओळख वाढवत आहे आणि तुम्हीही या प्लॅटफॉर्मवर सामील व्हा अशी माझी इच्छा आहे.\n\nतुमचा विमा व्यवसाय ऑनलाइन नेण्यासाठी माझ्या रेफरल लिंकवरून PadosiAgent वर सामील व्हा 🚀\n\n👉 {{referral_link}}"
            },
            {
                'id': 'mr_2',
                'title': '५०% विशेष सवलત',
                'text': "PadosiAgent च्या विशेष मोहिमेत 50% सवलतीचा लाभ घ्या आणि ऑनलाइन व्हा:\n{{referral_link}}"
            },
            {
                'id': 'mr_3',
                'title': 'विमा व्यवसाय वाढवा',
                'text': "आपल्या परिसरातील नवीन ग्राहकांपर्यंत पोहोचण्यासाठी आजच नोंदणी करा:\n{{referral_link}}"
            },
            {
                'id': 'mr_4',
                'title': 'व्हेरिफाइड एजंट बॅज',
                'text': "अधिकृत विमा सल्लागाराची ओळख मिळवा आणि व्यवसाय वाढवा:\n{{referral_link}}"
            },
            {
                'id': 'mr_5',
                'title': 'थेट शिफारस',
                'text': "मी PadosiAgent वापरत आहे, आपणही जुळा आणि लाभ घ्या:\n{{referral_link}}"
            }
        ]
    },
    'ta': {
        'label': 'தமிழ் (Tamil)',
        'templates': [
            {
                'id': 'ta_1',
                'title': 'பரிந்துரை அழைப்பு (பரிந்துரை)',
                'text': "வணக்கம், நான் {{agent_name}}, காப்பீட்டு ஆலோசகர். 👋\n\nPadosiAgent மூலம் எனது டிஜிட்டல் இருப்பை வளர்த்து வருகிறேன்; நீங்களும் இந்த தளத்தில் சேர விரும்புகிறேன்.\n\nஉங்கள் காப்பீட்டு தொழிலை ஆன்லைனில் கொண்டு செல்ல எனது பரிந்துரை இணைப்பில் PadosiAgent-ஐ சேருங்கள் 🚀\n\n👉 {{referral_link}}"
            },
            {
                'id': 'ta_2',
                'title': '50% சிறப்பு தள்ளுபடி',
                'text': "PadosiAgent சாம்பியன்ஷிப் சிறப்பு சலுகையில் 50% தள்ளுபடி பெறுங்கள்:\n{{referral_link}}"
            },
            {
                'id': 'ta_3',
                'title': 'புதிய வாடிக்கையாளர்கள்',
                'text': "உங்கள் பகுதியில் உள்ள புதிய வாடிக்கையாளர்களை ஈர்க்க இப்போதே சேருங்கள்:\n{{referral_link}}"
            },
            {
                'id': 'ta_4',
                'title': 'சரிபார்க்கப்பட்ட பேட்ஜ்',
                'text': "சரிபார்க்கப்பட்ட காப்பீட்டு முகவராக அடையாளம் காணுங்கள்:\n{{referral_link}}"
            },
            {
                'id': 'ta_5',
                'title': 'நேரடி அழைப்பு',
                'text': "என் பரிந்துரை மூலம் சேர்ந்து உங்கள் தொழிலை வளர்த்துக் கொள்ளுங்கள்:\n{{referral_link}}"
            }
        ]
    },
    'te': {
        'label': 'తెలుగు (Telugu)',
        'templates': [
            {
                'id': 'te_1',
                'title': 'రెఫరల్ ఆహ్వానం (సిఫార్సు)',
                'text': "నమస్కారం, నేను {{agent_name}}, ఇన్సూరెన్స్ అడ్వైజర్. 👋\n\nనేను PadosiAgent తో నా డిజిటల్ ఉనికిని పెంచుకుంటున్నాను; మీరు కూడా ఈ ప్లాట్‌ఫామ్‌లో చేరాలని కోరుకుంటున్నాను.\n\nమీ ఇన్సూరెన్స్ వ్యాపారాన్ని ఆన్‌లైన్‌కు తీసుకెళ్లడానికి నా రెఫరల్ లింక్ ద్వారా PadosiAgent‌లో చేరండి 🚀\n\n👉 {{referral_link}}"
            },
            {
                'id': 'te_2',
                'title': '50% తగ్గింపు ఆఫర్',
                'text': "నేషనల్ ఛాంపియన్‌షిప్ ఆఫర్‌లో 50% తగ్గింపును పొందండి:\n{{referral_link}}"
            },
            {
                'id': 'te_3',
                'title': 'వ్యాపార వృద్ధి',
                'text': "మీ ప్రాంతంలో ఎక్కువ మంది కస్టమర్లను చేరుకోవడానికి చేరండి:\n{{referral_link}}"
            },
            {
                'id': 'te_4',
                'title': 'వెరిఫైడ్ బ్యాడ్జ్',
                'text': "వెరిఫైడ్ ఏజెంట్ గుర్తింపుతో నమ్మకాన్ని పెంచుకోండి:\n{{referral_link}}"
            },
            {
                'id': 'te_5',
                'title': 'ప్రత్యేక ఆహ్వానం',
                'text': "నా ఆహ్వాన లింక్ ద్వారా చేరి ప్రయోజనం పొందండి:\n{{referral_link}}"
            }
        ]
    },
    'bn': {
        'label': 'বাংলা (Bengali)',
        'templates': [
            {
                'id': 'bn_1',
                'title': 'রেফারেল আমন্ত্রণ (সুপারিশ)',
                'text': "নমস্কার, আমি {{agent_name}}, ইনসিওরেন্স এজেন্ট। 👋\n\nআমি PadosiAgent-এর সাথে আমার ডিজিটাল উপস্থিতি বাড়াচ্ছি এবং আপনাকেও এই প্ল্যাটফর্মে যোগ দিতে চাই।\n\nআপনার ইনস্যুরেন্স ব্যবসা অনলাইনে নিতে আমার রেফারেল লিঙ্ক দিয়ে PadosiAgent-এ যোগ দিন 🚀\n\n👉 {{referral_link}}"
            },
            {
                'id': 'bn_2',
                'title': '৫০% বিশেষ ছাড়',
                'text': "PadosiAgent ক্যাম্পেইনে বিশেষ ৫০% ছাড়ের সুযোগ নিন:\n{{referral_link}}"
            },
            {
                'id': 'bn_3',
                'title': 'নতুন গ্রাহকদের কাছে পৌঁছান',
                'text': "আপনার এলাকায় নতুন গ্রাহকদের দৃষ্টি আকর্ষণ করতে এখনই যোগ দিন:\n{{referral_link}}"
            },
            {
                'id': 'bn_4',
                'title': 'ভেরিফায়েড ব্যাজ',
                'text': "ভেরিফায়েড ইন্স্যুরেন্স এজেন্টের সম্মান ও পরিচয় লাভ করুন:\n{{referral_link}}"
            },
            {
                'id': 'bn_5',
                'title': 'সরাসরি আমন্ত্রণ',
                'text': "আমার রেফারেল লিঙ্ক দিয়ে আজই যুক্ত হোন:\n{{referral_link}}"
            }
        ]
    },
    'ml': {
        'label': 'മലയാളം (Malayalam)',
        'templates': [
            {
                'id': 'ml_1',
                'title': 'റഫറൽ ക്ഷണം (ശുപാർശ)',
                'text': "നമസ്കാരം, ഞാൻ {{agent_name}}, ഇൻഷുറൻസ് ഏജന്റ് ആണ്. 👋\n\nഞാൻ PadosiAgent ഉപയോഗിച്ച് എന്റെ ഡിജിറ്റൽ സാന്നിധ്യം വളർത്തുന്നു; നിങ്ങളും ഈ പ്ലാറ്റ്‌ഫോമിൽ ചേരണമെന്ന് ആഗ്രഹിക്കുന്നു.\n\nനിങ്ങളുടെ ഇൻഷുറൻസ് ബിസിനസ് ഓൺലൈനാക്കാൻ എന്റെ റഫറൽ ലിങ്ക് വഴി PadosiAgent-ൽ ചേരൂ 🚀\n\n👉 {{referral_link}}"
            },
            {
                'id': 'ml_2',
                'title': '50% പ്രത്യേക ഇളവ്',
                'text': "PadosiAgent നാഷണൽ കാമ്പെയ്നിൽ 50% കിഴിവ് സ്വന്തമാക്കൂ:\n{{referral_link}}"
            },
            {
                'id': 'ml_3',
                'title': 'ബിസിനസ് വളർത്താം',
                'text': "കൂടുതൽ ഉപഭോക്താക്കളിലേക്ക് എത്താൻ ഇന്ന് തന്നെ രജിസ്റ്റർ ചെയ്യൂ:\n{{referral_link}}"
            },
            {
                'id': 'ml_4',
                'title': 'വെരിഫൈഡ് ബാഡ്ജ്',
                'text': "വിശ്വാസ്യതയും അംഗീകാരവും നേടൂ:\n{{referral_link}}"
            },
            {
                'id': 'ml_5',
                'title': 'നേരിട്ടുള്ള ക്ഷണം',
                'text': "എന്റെ റഫറൽ ലിങ്കിലൂടെ പങ്കുചേരൂ:\n{{referral_link}}"
            }
        ]
    },
    'kn': {
        'label': 'ಕನ್ನಡ (Kannada)',
        'templates': [
            {
                'id': 'kn_1',
                'title': 'ರೆಫರಲ್ ಆಹ್ವಾನ (ಶಿಫಾರಸು)',
                'text': "ನಮಸ್ಕಾರ, ನಾನು {{agent_name}}, ವಿಮಾ ಸಲಹೆಗಾರ. 👋\n\nನಾನು PadosiAgent ಜೊತೆ ನನ್ನ ಡಿಜಿಟಲ್ ಹಾಜರಿ ಹೆಚ್ಚಿಸುತ್ತಿದ್ದೇನೆ; ನೀವೂ ಈ ವೇದಿಕೆಯಲ್ಲಿ ಸೇರಲಿ ಎಂದು ಬಯಸುತ್ತೇನೆ.\n\nನಿಮ್ಮ ವಿಮಾ ವ್ಯವಹಾರವನ್ನು ಆನ್‌ಲೈನ್‌ಗೆ ತರಲು ನನ್ನ ರೆಫರಲ್ ಲಿಂಕ್ ಮೂಲಕ PadosiAgent ಗೆ ಸೇರಿ 🚀\n\n👉 {{referral_link}}"
            },
            {
                'id': 'kn_2',
                'title': '50% ರಿಯಾಯಿತಿ ಆಫರ್',
                'text': "PadosiAgent ಚಾಂಪಿಯನ್‌ಶಿಪ್‌ನಲ್ಲಿ 50% ರಿಯಾಯಿತಿ ಪಡೆಯಿರಿ:\n{{referral_link}}"
            },
            {
                'id': 'kn_3',
                'title': 'ಹೊಸ ಗ್ರಾಹಕರನ್ನು ತಲುಪಿ',
                'text': "ನಿಮ್ಮ ವಿಮಾ ವ್ಯವಹಾರವನ್ನು ಆನ್‌ಲೈನ್‌ನಲ್ಲಿ ಬೆಳೆಸಲು ನೋಂದಾಯಿಸಿ:\n{{referral_link}}"
            },
            {
                'id': 'kn_4',
                'title': 'ವೆರಿಫೈಡ್ ಬ್ಯಾಡ್ಜ್',
                'text': "ಗ್ರಾಹಕರ ನಂಬಿಕೆಯನ್ನು ಹೆಚ್ಚಿಸಲು ವೆರಿಫೈಡ್ ಏಜೆಂಟ್ ಆಗಿ ಗುರುತಿಸಿಕೊಳ್ಳಿ:\n{{referral_link}}"
            },
            {
                'id': 'kn_5',
                'title': 'ನೇರ ಆಹ್ವಾನ',
                'text': "ನನ್ನ ಆಹ್ವಾನ ಲಿಂಕ್ ಬಳಸಿ ಇಂದೇ ಸೇರಿ:\n{{referral_link}}"
            }
        ]
    }
}


def render_whatsapp_message(template_text, agent_name, referral_link, profile_link, digital_price=999, professional_price=4999, discount=50):
    """Substitute dynamic variables in WhatsApp template text."""
    msg = template_text
    msg = msg.replace('{{agent_name}}', str(agent_name or 'Insurance Advisor'))
    msg = msg.replace('{{referral_link}}', str(referral_link or ''))
    msg = msg.replace('{{profile_link}}', str(profile_link or referral_link or ''))
    msg = msg.replace('{{digital_price}}', str(int(digital_price)))
    msg = msg.replace('{{professional_price}}', str(int(professional_price)))
    msg = msg.replace('{{discount}}', f"{discount}%")
    return msg


def get_whatsapp_share_url(rendered_message):
    """Generate the pre-filled WhatsApp share URL."""
    return f"https://api.whatsapp.com/send?text={quote(rendered_message)}"
