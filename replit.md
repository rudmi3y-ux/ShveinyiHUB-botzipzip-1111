# Telegram Bot for Sewing Workshop (Швейный HUB)

## Overview

A multi-functional Telegram bot for automating customer service at a sewing workshop. The system provides automated customer interactions through an AI assistant called "Иголочка" (Little Needle), order management, spam protection, and a web-based admin panel.

**Core Capabilities:**
- Order intake with photo uploads
- 24/7 automated Q&A via GigaChat AI integration
- Spam filtering and rate limiting
- Admin notifications for new orders
- Web dashboard for order and user management
- Knowledge base for pricing and FAQ responses

## User Preferences

Preferred communication style: Simple, everyday language.

## System Architecture

### Application Structure

The project follows a modular Python architecture with clear separation of concerns:

- **Main Bot (`main.py`)** - Telegram bot entry point using python-telegram-bot library with conversation handlers
- **Web Admin (`webapp/`)** - Flask-based admin dashboard with authentication
- **Handlers (`handlers/`)** - Separated command, message, order, and admin handlers
- **Utils (`utils/`)** - Database operations, AI integration, anti-spam, caching

### Bot Framework

**Technology:** python-telegram-bot v20.7

**Conversation Flow:**
- Uses `ConversationHandler` for multi-step order creation
- States: SELECT_SERVICE → SEND_PHOTO → ENTER_NAME → ENTER_PHONE → CONFIRM_ORDER
- Persistent menu with inline keyboards for navigation

**AI Integration:**
- GigaChat API for generating contextual responses
- Adaptive prompts based on user context and time of day
- Fallback to local knowledge base when AI fails
- Response caching to reduce API calls

### Web Admin Panel

**Technology:** Flask 3.0 with Gunicorn

**Features:**
- Session-based authentication (username/password from environment)
- Order management with status updates
- User listing with order counts
- Spam log viewer
- Review moderation
- CSV export functionality

**Security Measures:**
- `@requires_auth` decorator on all admin routes
- XSS protection via HTML escaping
- CSRF protection through Flask sessions

### Database Layer

**Technology:** SQLAlchemy ORM with PostgreSQL (via `DATABASE_URL` environment variable)

**Models:**
- `Order` - Service orders with status tracking
- `User` - Telegram users with preferences
- `Review` - Customer reviews with moderation status
- `SpamLog` - Blocked spam attempts
- `Category` / `Price` - Service catalog

**Key Functions:**
- Automatic user registration on first interaction
- Order status workflow: new → in_progress → completed → issued
- Daily visit tracking for personalized greetings

### Anti-Spam System

**Implementation:** Rate limiting + keyword blacklist

- Max 5 messages per 60 seconds per user
- Blacklist for advertising, gambling, adult content keywords
- Whitelist for sewing-related terms (prevents false positives)
- 5-minute mute for violators
- All blocked attempts logged to database

### Knowledge Base

**Storage:** Text files in `data/knowledge_base/`

**Categories:**
- Pricing by service type
- FAQ responses
- Contact information
- Delivery options

**Search:** Keyword matching with category-based organization

## External Dependencies

### APIs and Services

| Service | Purpose | Configuration |
|---------|---------|---------------|
| Telegram Bot API | Core bot functionality | `BOT_TOKEN` env var |
| GigaChat API | AI-powered responses | `GIGACHAT_CREDENTIALS` env var |
| PostgreSQL | Primary database | `DATABASE_URL` env var |

### Environment Variables Required

```
BOT_TOKEN - Telegram bot token from @BotFather
GIGACHAT_CREDENTIALS - Sber GigaChat API credentials
DATABASE_URL - PostgreSQL connection string
ADMIN_ID - Telegram user ID for admin access
ADMIN_USERNAME - Web admin login
ADMIN_PASSWORD - Web admin password
FLASK_SECRET_KEY - Session encryption key
```

### Python Dependencies

Core packages from `requirements.txt`:
- `python-telegram-bot==20.7` - Telegram bot framework
- `gigachat==0.1.29` - GigaChat AI client
- `flask==3.0.0` - Web framework
- `sqlalchemy==2.0.23` - Database ORM
- `psycopg2-binary==2.9.9` - PostgreSQL driver
- `gunicorn==22.0.0` - Production WSGI server

### Health Check Endpoint

Built-in HTTP server on port 8080 provides `/health` and `/status` endpoints for uptime monitoring, returning JSON with bot status and uptime.