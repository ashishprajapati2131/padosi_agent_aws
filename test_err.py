import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'padosi_agent.settings')
django.setup()
from chatbot.llm_client import stream_plain_text_completion
import traceback
gen = stream_plain_text_completion('test_session2', 'Find local agents?')
try:
    print(next(gen))
except Exception as e:
    traceback.print_exc()
