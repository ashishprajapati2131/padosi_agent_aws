import os
import json
import logging
import traceback
from groq import Groq, BadRequestError
from chatbot.models import ChatSession, ChatMessage, LatencyLog
from apps.home.views.pages import build_agent_query
import time
from django.utils.timezone import now

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are PadosiAgent Assistant, a helpful, polite, and knowledgeable AI assistant for an insurance and investment platform called PadosiAgent. 
Your primary goal is to assist users with insurance, investments, and finding the right agents.
If the user asks an off-topic, harmful, or inappropriate question, politely decline or redirect them to insurance, investments, or agent-finding topics.
Keep your responses concise and user-friendly.

When the user asks to find an insurance agent or someone to help them, use the `find_agents` tool to search the database. You should extract the relevant information from their request.

CRITICAL RULES FOR USING `find_agents` TOOL:
1. You must NEVER blindly guess the `service_type` or `insurance_type`. However, you SHOULD deduce them if reasonably implied by the user (e.g. 'claim' implies 'Claim Assistance', 'car' implies 'Motor', 'renew' implies 'Policy Review'). If they cannot be reasonably deduced, ask a clarifying question to gather the missing information BEFORE calling the find_agents tool.
2. If the user provides a numeric postal/zip code (e.g., '380016'), always pass it in the `pincode` field, never in `location`. Only use `location` for named places (city, area, locality).

Do not make up agent information without calling the tool.
"""

def get_groq_client():
    api_key = os.environ.get('GROQ_API_KEY')
    if not api_key:
        logger.warning("GROQ_API_KEY not set. LLM features will fail.")
    return Groq(api_key=api_key)

def generate_suggestion_chips():
    try:
        client = get_groq_client()
        prompt = "Generate exactly 3 short suggestion questions (under 8 words each) that a user might ask an insurance/investment assistant. Return them as a JSON array of strings. Cover a mix of insurance, investment, and agent-finding topics. ONLY output the raw JSON array without markdown formatting."
        
        start_time = time.time()
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=100,
        )
        total_time = time.time() - start_time
        
        # Log latency
        LatencyLog.objects.create(
            endpoint="generate_suggestion_chips",
            total_time=total_time
        )
        
        content = response.choices[0].message.content.strip()
        
        # Clean markdown fences if any
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
            
        chips = json.loads(content.strip())
        if isinstance(chips, list) and len(chips) == 3:
            return chips
    except Exception as e:
        logger.error(f"Error generating chips: {e}")
        
    # Fallback
    return [
        "Need help finding an agent?",
        "Explain Term Life vs Whole Life",
        "How do I file a health claim?"
    ]

def generate_quick_options(reply_text):
    if "?" not in reply_text:
        return []
    client = get_groq_client()
    prompt = f"""Analyze the following assistant reply. Does it ask the user a clarifying or follow-up question?
If yes, provide 2 to 4 short quick-reply options (under 6 words each) for the user to answer it.

CRITICAL RULE:
ONLY generate options if the question is asking for something from a limited, well-known set of choices (e.g. Insurance type, Yes/No, or a specific list of categories).
DO NOT generate options (return an empty list []) if the question is strictly open-ended or asking for free-text information (e.g. City/Location, Name, Phone number).
If the assistant explicitly lists choices in the text (e.g. "Health, Life, Motor"), your options MUST strictly match those provided choices. If the assistant asks for a category but doesn't list choices (e.g. "What type of insurance?"), generate 2-4 sensible, common options for that category.
If the question is compound (asks for both a bounded choice AND an open-ended detail like location), generate options for the bounded part.

Return ONLY valid JSON.
Schema: {{"is_question": boolean, "options": ["Option 1", "Option 2"]}}

Reply to analyze:
"{reply_text}"
"""
    try:
        start_time = time.time()
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=150,
            response_format={"type": "json_object"}
        )
        LatencyLog.objects.create(
            endpoint="generate_quick_options",
            total_time=time.time() - start_time
        )
        
        content = response.choices[0].message.content.strip()
        data = json.loads(content)
        if data.get("is_question") and isinstance(data.get("options"), list):
            return data["options"][:4]
    except Exception as e:
        logger.error(f"Error generating quick options: {e}")
    return []

def _finalize_response(session, final_content):
    ChatMessage.objects.create(session=session, role="assistant", content=final_content)
    quick_options = generate_quick_options(final_content)
    return {"reply": final_content, "quick_options": quick_options}

def get_chat_completion(session_id, user_message):
    client = get_groq_client()
    
    # Get or create session
    session, _ = ChatSession.objects.get_or_create(session_id=session_id)
    
    # Save user message
    ChatMessage.objects.create(session=session, role="user", content=user_message)
    
    # Fetch context (last 10 messages)
    history_qs = ChatMessage.objects.filter(session=session).order_by('-timestamp')[:10]
    history = list(history_qs)
    history.reverse()
    
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for msg in history:
        m = {"role": msg.role, "content": msg.content or ""}
        if msg.role == 'tool':
            m["tool_call_id"] = msg.tool_call_id
            m["name"] = msg.tool_name
        messages.append(m)
        
    tools = [
        {
            "type": "function",
            "function": {
                "name": "find_agents",
                "description": "Find insurance agents based on user criteria.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "location": {
                            "type": "string",
                            "description": "The city or area the user is looking for agents in."
                        },
                        "pincode": {
                            "type": "string",
                            "description": "The 6-digit postal code/zip code the user is looking for agents in."
                        },
                        "service_type": {
                            "type": "string",
                            "enum": ["New Policy", "Claim Assistance", "Policy Review"],
                            "description": "The type of service the user needs."
                        },
                        "insurance_type": {
                            "type": "string",
                            "description": "The type of insurance (e.g. Health, Life, Motor, Travel)."
                        }
                    },
                    "required": ["service_type", "insurance_type"]
                }
            }
        }
    ]

    user_msg_lower = user_message.lower()
    needs_agent = any(k in user_msg_lower for k in ["find", "search", "agent", "looking for", "help me find", "need someone"])
    current_tool_choice = {"type": "function", "function": {"name": "find_agents"}} if needs_agent else "auto"

    try:
        start_time = time.time()
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            tools=tools,
            tool_choice=current_tool_choice,
        )
        total_time = time.time() - start_time
        
        # Log latency
        LatencyLog.objects.create(
            endpoint="chat_completion",
            total_time=total_time
        )
        
        response_message = response.choices[0].message
        tool_calls = response_message.tool_calls
        if tool_calls:
            messages.append(response_message)
            tool_call = tool_calls[0]
            function_name = tool_call.function.name
            function_args = json.loads(tool_call.function.arguments)
            
            if function_name == "find_agents":
                location = function_args.get("location", "")
                pincode = function_args.get("pincode", "")
                service_type = function_args.get("service_type", "")
                insurance_type = function_args.get("insurance_type", "")
                
                service_types = [service_type] if service_type else []
                insurance_types = [insurance_type] if insurance_type else []
                
                try:
                    agents, _, _, _ = build_agent_query(
                        pincode=pincode, location=location, lat="", lng="", detected_area=location,
                        service_type_input=service_types, insurance_type_input=insurance_types,
                        insurance_company_input=[], claim_company_input="", search_val="", sort_by=""
                    )
                    
                    if not agents:
                        result_msg = f"No agents found for criteria: {function_args}"
                    else:
                        top_agents = agents[:3]
                        result_parts = []
                        for idx, a in enumerate(top_agents):
                            result_parts.append(f"{idx+1}. {a.fullname} (Match: {a.match_percent}%, Reviews: {a.review_count_val})")
                        result_msg = "Found these top agents:\n" + "\n".join(result_parts)
                except Exception as e:
                    logger.error(f"Error querying agents: {e}")
                    traceback.print_exc()
                    result_msg = "Error executing find_agents tool."
                
                messages.append(
                    {
                        "tool_call_id": tool_call.id,
                        "role": "tool",
                        "name": function_name,
                        "content": result_msg,
                    }
                )
                
                # Save tool response
                ChatMessage.objects.create(session=session, role="tool", content=result_msg, tool_call_id=tool_call.id, tool_name=function_name)

                # Send back to LLM to get final text
                start_time2 = time.time()
                second_response = client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=messages,
                )
                LatencyLog.objects.create(
                    endpoint="chat_completion_tool_final",
                    total_time=time.time() - start_time2
                )
                final_content = second_response.choices[0].message.content
                return _finalize_response(session, final_content)
        else:
            final_content = response_message.content
            return _finalize_response(session, final_content)
            
    except BadRequestError as e:
        err_str = str(e).lower()
        if "tool_use_failed" in err_str or "failed to parse" in err_str:
            logger.warning(f"Groq tool use failed, retrying without tools: {e}")
            try:
                fallback_response = client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=messages,
                )
                final_content = fallback_response.choices[0].message.content
                return _finalize_response(session, final_content)
            except Exception as inner_e:
                logger.error(f"Error in chat completion fallback: {inner_e}")
                return {"reply": "I'm having trouble connecting right now. Please try again later.", "quick_options": []}
        else:
            logger.error(f"Groq BadRequestError: {e}")
            return {"reply": "I'm having trouble connecting right now. Please try again later.", "quick_options": []}
    except Exception as e:
        logger.error(f"Error in chat completion: {e}")
        return {"reply": "I'm having trouble connecting right now. Please try again later.", "quick_options": []}
