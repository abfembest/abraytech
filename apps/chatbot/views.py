# Create your views here.
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie
import json
import random
from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_GET
from django.views.decorators.csrf import csrf_protect
from django.utils import timezone
from django.views.decorators.cache import never_cache
# from django.core.validators import validate_email
# from django.core.exceptions import ValidationError
# from django.views.decorators.debug import sensitive_post_parameters
from .models import ChatSession, ChatMessage, IntentResponse
from .services import IntentClassifier
from django.conf import settings
from django.core.cache import cache
import re


@ensure_csrf_cookie
def index(request):
    return render(request, 'chatbot/chatbot.html')


def sanitize_input(text):
    return text.strip()[:500]  # length limit


def generate_captcha():
    """Return a (question_str, answer_int) math captcha pair — gates guest chat sessions."""
    num1 = random.randint(1, 10)
    num2 = random.randint(1, 10)
    op = random.choice(['+', '-', '*'])
    if op == '+':
        answer = num1 + num2
    elif op == '-':
        if num2 > num1:
            num1, num2 = num2, num1
        answer = num1 - num2
    else:
        answer = num1 * num2
    return f"{num1} {op} {num2}", answer


def rate_limit(key_prefix, limit=10, period=60):
    def decorator(view):
        def wrapped(request, *args, **kwargs):
            ip = request.META.get('REMOTE_ADDR')
            cache_key = f"{key_prefix}_{ip}"
            count = cache.get(cache_key, 0)
            if count >= limit:
                return JsonResponse({'error': 'Rate limit exceeded'}, status=429)
            cache.set(cache_key, count + 1, period)
            return view(request, *args, **kwargs)
        return wrapped
    return decorator



def get_active_session(session_id):
    try:
        session = ChatSession.objects.get(id=session_id, is_active=True)
        # check inactivity timeout
        timeout = getattr(settings, 'CHAT_SESSION_TIMEOUT_MINUTES', 15)
        if (timezone.now() - session.last_activity).total_seconds() > timeout * 60:
            session.close()
            return None
        return session
    except ChatSession.DoesNotExist:
        return None




@require_GET
@never_cache
@rate_limit('chatbot_captcha', limit=20, period=60)
def get_captcha(request):
    """Issues a bot-check challenge for the guest pre-chat gate (see start_session)."""
    question, answer = generate_captcha()
    request.session['chatbot_captcha_answer'] = answer
    return JsonResponse({'question': question})


# --- Original guest-identification flow (name + email, no bot check) ---
# Kept for reference in case we need to bring back name/email collection.
# @sensitive_post_parameters('email')
# @require_POST
# @csrf_protect
# @rate_limit('start_session', limit=5, period=60)
# def start_session(request):
#     data = json.loads(request.body)
#     first_name = sanitize_input(data.get('first_name', ''))
#     email = data.get('email', '')
#
#     if not first_name or not email:
#         return JsonResponse({'error': 'Name and email required'}, status=400)
#
#     try:
#         validate_email(email)
#     except ValidationError:
#         return JsonResponse({'error': 'Invalid email'}, status=400)
#
#     # close any existing active sessions for this email? (optional)
#     # For simplicity, always create new
#     session = ChatSession.objects.create(first_name=first_name, email=email)
#
#     # Add a welcome message from bot
#     welcome = "Welcome! I'm your Student Life Assistant. How can I help you today?"
#     ChatMessage.objects.create(session=session, sender='bot', content=welcome)
#
#     return JsonResponse({
#         'session_id': session.id,
#         'first_name': session.first_name,
#         'messages': [{
#             'sender': 'bot',
#             'content': welcome,
#             'timestamp': session.started_at.isoformat()
#         }]
#     })


@require_POST
@csrf_protect
@rate_limit('start_session', limit=5, period=60)
def start_session(request):
    data = json.loads(request.body)

    if request.user.is_authenticated:
        # Logged-in users are already verified — no bot check needed, and
        # identity comes from the session, never from client-posted values.
        first_name = request.user.first_name or request.user.username
        email = request.user.email
    else:
        # Guests: bot check is the gate, not a name/email form.
        session_answer = request.session.get('chatbot_captcha_answer')
        user_answer = str(data.get('captcha', '')).strip()
        try:
            if int(user_answer) != int(session_answer):
                return JsonResponse({'error': 'Incorrect answer. Please try the bot check again.'}, status=400)
        except (ValueError, TypeError):
            return JsonResponse({'error': 'Invalid answer. Please enter a number.'}, status=400)
        request.session.pop('chatbot_captcha_answer', None)
        first_name = ''
        email = ''

    session = ChatSession.objects.create(first_name=first_name, email=email)

    # Add a welcome message from bot
    welcome = "Welcome! I'm your Student Life Assistant. How can I help you today?"
    ChatMessage.objects.create(session=session, sender='bot', content=welcome)

    return JsonResponse({
        'session_id': session.id,
        'first_name': session.first_name,
        'messages': [{
            'sender': 'bot',
            'content': welcome,
            'timestamp': session.started_at.isoformat()
        }]
    })


@require_POST
@csrf_protect
@rate_limit('send_message', limit=30, period=60)
def send_message(request):
    data = json.loads(request.body)
    session_id = data.get('session_id')
    message = sanitize_input(data.get('message', ''))
    message = message.lower()
    message = message.strip()
    message = re.sub(r"\s+", " ", message)
    if not session_id or not message:
        return JsonResponse({'error': 'Missing data'}, status=400)

    session = get_active_session(session_id)
    if not session:
        return JsonResponse({'error': 'Session expired or invalid'}, status=401)

    # Save user message
    ChatMessage.objects.create(session=session, sender='user', content=message)

    # Update last_activity
    session.save()  # auto_now updates
    # Get bot response
    intent, confidence = IntentClassifier.predict(message)
    try:
        response_obj = IntentResponse.objects.get(intent=intent)
        bot_response = response_obj.response_text
    except IntentResponse.DoesNotExist:
        bot_response = "I'm sorry, I don't have an answer for that."

    # Save bot message
    ChatMessage.objects.create(session=session, sender='bot', content=bot_response)

    return JsonResponse({
        'intent': intent,
        'confidence': confidence,
        'response': bot_response,
        'session_id': session.id
    })


@require_POST
@csrf_protect
def close_session(request):
    data = json.loads(request.body)
    session_id = data.get('session_id')
    if not session_id:
        return JsonResponse({'error': 'Missing session_id'}, status=400)
    try:
        session = ChatSession.objects.get(id=session_id, is_active=True)
        session.close()
        return JsonResponse({'status': 'closed'})
    except ChatSession.DoesNotExist:
        return JsonResponse({'error': 'Session not found'}, status=404)


@never_cache
def session_status(request):
    session_id = request.GET.get('session_id')
    if not session_id:
        return JsonResponse({'active': False})
    session = get_active_session(session_id)
    if not session:
        return JsonResponse({'active': False})
    messages = ChatMessage.objects.filter(session=session).values('sender', 'content', 'timestamp')
    return JsonResponse({
        'active': True,
        'session_id': session.id,
        'first_name': session.first_name,
        'messages': list(messages)
    })