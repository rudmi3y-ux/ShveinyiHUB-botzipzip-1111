import os
import logging
from config import WORKSHOP_PHONE
from gigachat import GigaChat
from gigachat.models import Chat, Messages, MessagesRole
from .cache import cache
from .knowledge_loader import knowledge
from .adaptive_prompts import generate_adaptive_prompt, get_context_summary, detect_topic, analyze_question_complexity
from .database import get_user_context, save_chat_history

logger = logging.getLogger(__name__)

MAX_TOKENS = 100


class GigaChatAPI:
    def __init__(self):
        self.client = None
        self._init_client()
    
    def _init_client(self):
        """Initialize GigaChat client"""
        try:
            credentials = os.getenv('GIGACHAT_CREDENTIALS')
            if not credentials:
                logger.warning("GIGACHAT_CREDENTIALS not set. GigaChat disabled.")
                return
            
            self.client = GigaChat(
                credentials=credentials,
                verify_ssl_certs=False
            )
            logger.info("GigaChat client initialized")
        except Exception as e:
            logger.error(f"Failed to initialize GigaChat: {e}")
    
    def _get_fallback_response(self, message: str) -> tuple[str, bool]:
        """
        Попытка найти ответ в базе знаний.
        Возвращает (ответ, found).
        """
        try:
            fallback = knowledge.search_knowledge(message)
            if fallback:
                logger.info(f"Fallback answer found for: {message[:30]}")
                return fallback, True
        except Exception as e:
            logger.error(f"Fallback search error: {e}")
        return None, False
    
    async def get_response(self, message: str, user_id: int = None) -> tuple[str, bool]:
        """
        Get response from GigaChat with adaptive prompts and context.
        Returns (response_text, needs_human_help) tuple.
        needs_human_help=True when AI couldn't give a good answer.
        """
        needs_human = False
        
        if not self.client:
            fallback, found = self._get_fallback_response(message)
            if found:
                return fallback, False
            return f"Извините, сервис временно недоступен. Позвоните нам: {WORKSHOP_PHONE}", True
        
        try:
            user_context = get_user_context(user_id) if user_id else {
                'is_new': True, 'tone': 'friendly', 'questions_count': 0, 
                'recent_topics': [], 'name': None
            }
            
            adaptive_prompt = generate_adaptive_prompt(user_context, message)
            knowledge_text = knowledge.get_all_knowledge()[:2500]
            full_system_prompt = adaptive_prompt + knowledge_text
            
            context_info = get_context_summary(user_context, message)
            logger.info(f"Adaptive context: {context_info}")
            
            payload = Chat(
                messages=[
                    Messages(
                        role=MessagesRole.SYSTEM,
                        content=full_system_prompt
                    ),
                    Messages(
                        role=MessagesRole.USER,
                        content=message
                    )
                ],
                max_tokens=MAX_TOKENS,
                temperature=0.7
            )
            
            response = self.client.chat(payload)
            logger.info(f"GigaChat response received for: {message[:30]}")
            
            if response and hasattr(response, 'choices') and response.choices:
                answer = response.choices[0].message.content
                
                if user_id:
                    topic = detect_topic(message)
                    complexity = analyze_question_complexity(message)
                    save_chat_history(user_id, message, answer, topic, complexity)
                
                needs_human = self._check_needs_human(message, answer)
                return answer, needs_human
            
            fallback, found = self._get_fallback_response(message)
            if found:
                return fallback, False
            
            return f"Не удалось получить ответ. Попробуйте переформулировать вопрос или позвоните: {WORKSHOP_PHONE}", True
        except Exception as e:
            logger.error(f"GigaChat error: {e}")
            
            fallback, found = self._get_fallback_response(message)
            if found:
                return fallback, False
            
            return f"Ой, что-то пошло не так 🧵 Попробуйте позже или позвоните нам: {WORKSHOP_PHONE}", True
    
    def _check_needs_human(self, question: str, answer: str) -> bool:
        """Определяет, нужна ли помощь человека"""
        complex_keywords = [
            'сложн', 'особ', 'нестандарт', 'индивидуальн',
            'срочно', 'сегодня', 'консультац', 'записаться',
            'жалоб', 'претенз', 'брак', 'переделать'
        ]
        
        question_lower = question.lower()
        for keyword in complex_keywords:
            if keyword in question_lower:
                return True
        
        uncertain_phrases = [
            'не могу', 'затрудняюсь', 'сложно сказать',
            'нужно посмотреть', 'зависит от', 'уточнить'
        ]
        answer_lower = answer.lower()
        for phrase in uncertain_phrases:
            if phrase in answer_lower:
                return True
        
        return False


gigachat = GigaChatAPI()


async def get_ai_response(text: str, user_id: int = None) -> tuple[str, bool]:
    """
    Get AI response from GigaChat with adaptive context.
    Returns (response_text, needs_human_help) tuple.
    """
    return await gigachat.get_response(text, user_id)
