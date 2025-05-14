from fastapi import FastAPI, Request, Depends, Form, HTTPException, status, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from starlette.middleware.sessions import SessionMiddleware
from fastapi.templating import Jinja2Templates
import httpx
from pydantic_settings import BaseSettings
import logging
from jose import jwt
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import feedparser
import asyncio
import requests

# Import both legacy table references and new ORM models
from database import (
    # Legacy table references for compatibility
    SessionLocal, users, user_arxiv_topics, user_book_categories, favourites,
    # Session management
    get_db, get_db_session,
    # ORM models
    User, UserArxivTopic, UserBookCategory, Favorite
)
from constants import BOOK_CATEGORIES, ARXIV_TAXONOMY

# =====================
# Environment Settings
# =====================
class Settings(BaseSettings):
    GOOGLE_CLIENT_ID: str
    GOOGLE_CLIENT_SECRET: str
    SESSION_SECRET: str
    DATABASE_URL: str
    BASE_URL: str = "http://localhost:8000"  # Default for local, override in Render
    RSS_CACHE_TTL: int = 1800  # 30 minutes cache for RSS feeds
    ADMIN_EMAIL: str  # Add admin email from .env
    class Config:
        env_file = ".env"
settings = Settings()

# =====================
# FastAPI App & Middleware
# =====================
app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=settings.SESSION_SECRET)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory="static"), name="static")

# =====================
# Templates
# =====================
templates = Jinja2Templates(directory="templates")

# =====================
# Helper: Verify Google JWT signature
# =====================
def verify_google_jwt(id_token):
    try:
        resp = requests.get('https://www.googleapis.com/oauth2/v3/certs')
        keys = resp.json()['keys']
        header = jwt.get_unverified_header(id_token)
        kid = header['kid']
        key = next((k for k in keys if k['kid'] == kid), None)
        if not key:
            raise Exception('Public key not found in Google certs')
        payload = jwt.decode(
            id_token,
            key,
            algorithms=['RS256'],
            audience=settings.GOOGLE_CLIENT_ID,
            options={"verify_at_hash": False}
        )
        return payload
    except Exception as e:
        logging.error(f'JWT verification failed: {e}')
        return None

# =====================
# Helper: Get current user from session
# =====================
def get_current_user(request: Request):
    email = request.session.get("user")
    if not email:
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/"})
    return email

# =====================
# Feed Cache System
# =====================
class FeedCache:
    def __init__(self):
        self.cache = {}
        self.last_update = {}

    async def fetch_google_books(self, category_id: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """
        Fetch latest books from Google Books API for a given category, with configurable max_results
        """
        url = f"https://www.googleapis.com/books/v1/volumes?q=subject:{category_id}&orderBy=newest&maxResults={max_results}"
        items = []
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, timeout=10.0)
                response.raise_for_status()
                data = response.json()
                for book in data.get('items', []):
                    volume = book.get('volumeInfo', {})
                    published = volume.get('publishedDate', '')
                    items.append({
                        'title': volume.get('title', ''),
                        'link': volume.get('infoLink', ''),
                        'summary': volume.get('description', ''),
                        'published': published,
                        'type': 'book',
                        'category': category_id,
                        'authors': ', '.join(volume.get('authors', [])),
                        'thumbnail': volume.get('imageLinks', {}).get('thumbnail', ''),
                    })
        except Exception as e:
            print(f"Error fetching Google Books API: {e}")
        return items

    async def fetch_book_feeds(self, categories: List[str], max_results: int = 10) -> List[Dict[str, Any]]:
        """
        Fetch latest books from Google Books API for each selected category (by book_category_id)
        """
        if not categories:
            return []
        feed_items = []
        tasks = []
        for category in categories:
            tasks.append(self.fetch_google_books(category, max_results=max_results))
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, Exception):
                    print(f"Error fetching Google Books: {result}")
                else:
                    feed_items.extend(result)
        return feed_items

    async def fetch_arxiv_api(self, category_code: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """
        Fetch latest research papers from arXiv API for a given category, with configurable max_results
        """
        base_url = "http://export.arxiv.org/api/query"
        query = f"search_query=cat:{category_code}&sortBy=submittedDate&sortOrder=descending&start=0&max_results={max_results}"
        url = f"{base_url}?{query}"
        items = []
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, timeout=10.0)
                response.raise_for_status()
                feed = feedparser.parse(response.text)
                for entry in feed.entries:
                    published = entry.get('published', entry.get('updated', ''))
                    authors = ', '.join([a.get('name', '') for a in entry.get('authors', [])])
                    summary = entry.get('summary', '')
                    items.append({
                        'title': entry.get('title', ''),
                        'link': entry.get('link', ''),
                        'summary': summary,
                        'published': published,
                        'type': 'arxiv',
                        'category': category_code,
                        'authors': authors
                    })
        except Exception as e:
            print(f"Error fetching arXiv API: {e}")
        return items

    async def fetch_arxiv_feeds(self, topics: List[str], max_results: int = 10) -> List[Dict[str, Any]]:
        """
        Fetch latest research papers from arXiv API for each selected topic (by arxiv_topic_id)
        """
        if not topics:
            return []
        feed_items = []
        tasks = []
        for topic in topics:
            tasks.append(self.fetch_arxiv_api(topic, max_results=max_results))
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, Exception):
                    print(f"Error fetching arXiv: {result}")
                else:
                    feed_items.extend(result)
        # Remove duplicates by link
        seen = set()
        unique = []
        for item in feed_items:
            if item['link'] not in seen:
                seen.add(item['link'])
                unique.append(item)
        return unique

    async def get_feeds(self, user_email: str, book_categories: List[str], arxiv_topics: List[str], max_results: int = 10) -> List[Dict[str, Any]]:
        cache_key = f"{user_email}:{','.join(sorted(book_categories))}:{','.join(sorted(arxiv_topics))}:{max_results}"
        now = datetime.now()
        if (cache_key in self.cache and cache_key in self.last_update and
            (now - self.last_update[cache_key]).total_seconds() < settings.RSS_CACHE_TTL):
            return self.cache[cache_key]
        book_results, arxiv_results = await asyncio.gather(
            self.fetch_book_feeds(book_categories, max_results=max_results),
            self.fetch_arxiv_feeds(arxiv_topics, max_results=max_results),
            return_exceptions=True
        )
        if isinstance(book_results, Exception):
            book_results = []
        if isinstance(arxiv_results, Exception):
            arxiv_results = []
        combined = book_results + arxiv_results
        combined = sorted(
            combined,
            key=lambda x: x.get('published', ''),
            reverse=True
        )
        self.cache[cache_key] = combined
        self.last_update[cache_key] = now
        return combined

    def invalidate(self, user_email: str = None):
        if user_email:
            keys_to_remove = [k for k in self.cache if k.startswith(f"{user_email}:")]
            for key in keys_to_remove:
                self.cache.pop(key, None)
                self.last_update.pop(key, None)
        else:
            self.cache = {}
            self.last_update = {}

# Initialize the cache
feed_cache = FeedCache()

# =====================
# Routes
# =====================
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/auth/login")
async def login():
    google_auth_url = (
        f"https://accounts.google.com/o/oauth2/auth?"
        f"client_id={settings.GOOGLE_CLIENT_ID}&"
        f"redirect_uri={settings.BASE_URL}/auth/callback?mode=login&"
        f"response_type=code&"
        f"scope=openid%20email&"
        f"access_type=offline"
    )
    return RedirectResponse(url=google_auth_url)

@app.get("/auth/signup")
async def signup():
    google_auth_url = (
        f"https://accounts.google.com/o/oauth2/auth?"
        f"client_id={settings.GOOGLE_CLIENT_ID}&"
        f"redirect_uri={settings.BASE_URL}/auth/callback?mode=signup&"
        f"response_type=code&"
        f"scope=openid%20email&"
        f"access_type=offline"
    )
    return RedirectResponse(url=google_auth_url)

@app.get("/logout")
async def logout(request: Request, user: str = Depends(get_current_user)):
    request.session.clear()
    return RedirectResponse(url="/")

@app.get("/auth/callback")
async def auth_callback(request: Request, code: str, mode: str = "login"):
    token_url = "https://oauth2.googleapis.com/token"
    data = {
        "code": code,
        "client_id": settings.GOOGLE_CLIENT_ID,
        "client_secret": settings.GOOGLE_CLIENT_SECRET,
        "redirect_uri": f"{settings.BASE_URL}/auth/callback?mode={mode}",
        "grant_type": "authorization_code",
    }
    try:
        async with httpx.AsyncClient() as client:
            token_response = await client.post(token_url, data=data)
            token_data = token_response.json()
            id_token = token_data.get("id_token")
            if not id_token:
                return HTMLResponse("<h2>Google authentication failed. Please try again.</h2>")
            payload = verify_google_jwt(id_token)
            if not payload:
                return HTMLResponse("<h2>Invalid Google token. Please try again.</h2>")
            email = payload.get("email")
            if not email:
                return HTMLResponse("<h2>Email not found in Google account.</h2>")            
            request.session["user"] = email

            # Handle admin differently
            if email == settings.ADMIN_EMAIL:
                with get_db_session() as db:
                    # For admin, check if they exist and create if not
                    admin_user = db.query(User).filter(User.email == email).first()
                    if not admin_user and mode == "signup":
                        # Create admin user
                        User.create(db, email=email)
                        # No need to force admin to select preferences
                    
                    # Redirect to admin panel regardless of login/signup
                    return RedirectResponse(url="/admin")
            
            with get_db_session() as db:
                # Find user by email
                user = db.query(User).filter(User.email == email).first()
                
                if mode == "signup":
                    if user:
                        return HTMLResponse("<h2>User already exists. Please login.</h2>")
                    # Create new user with helper method
                    User.create(db, email=email)
                    return RedirectResponse(url="/select-books")
                else:
                    if not user:
                        return HTMLResponse("<h2>No account found. Please signup first.</h2>")
                    
                    # Check if user has selected categories
                    book_cat = db.query(UserBookCategory).filter(UserBookCategory.user_email == email).first()
                    if not book_cat:
                        return RedirectResponse(url="/select-books")
                        
                    arxiv_cat = db.query(UserArxivTopic).filter(UserArxivTopic.user_email == email).first()
                    if not arxiv_cat:
                        return RedirectResponse(url="/select-research")
                        
                    return RedirectResponse(url="/home")
    except Exception as e:
        logging.error(f"OAuth callback error: {e}")
        return HTMLResponse("<h2>Authentication error. Please try again later.</h2>")

# ===============
# ADMIN ONLY DEPENDENCY
# ===============
def admin_required(request: Request):
    email = request.session.get("user")
    if email != settings.ADMIN_EMAIL:
        raise HTTPException(status_code=403, detail="Not authorized")
    return email

# ===============
# ADMIN PAGE
# ===============
@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request, admin: str = Depends(admin_required)):
    try:
        with get_db_session() as db:
            # Eagerly load user data to prevent detached instance errors
            users_list = []
            for user in db.query(User).all():
                users_list.append({
                    "email": user.email,
                    "created_at": user.created_at
                })
            
            # Load all favorites and organize by user
            all_favs = db.query(Favorite).all()
            favs_by_user = {}
            for fav in all_favs:
                # Create a dictionary with the favorite data to prevent detached instance errors
                fav_dict = {
                    "id": fav.id,
                    "title": fav.title,
                    "type": fav.type,
                    "link": fav.link,
                    "date_published": fav.date_published
                }
                favs_by_user.setdefault(fav.user_email, []).append(fav_dict)
        
        return templates.TemplateResponse("admin.html", {
            "request": request,
            "users": users_list,
            "favs_by_user": favs_by_user,
            "admin_email": settings.ADMIN_EMAIL
        })
    except Exception as e:
        logging.error(f"Admin page error: {e}")
        return HTMLResponse(f"<h2>Error loading admin page. Please try again later.</h2><p>Error: {str(e)}</p>")

# ===============
# ADMIN: DELETE USER
# ===============
@app.post("/admin/delete-user")
async def admin_delete_user(request: Request, user_email: str = Form(...), admin: str = Depends(admin_required)):
    try:
        with get_db_session() as db:
            # Check if user exists
            user = db.query(User).filter(User.email == user_email).first()
            if not user:
                return HTMLResponse("<h2>Error: User not found.</h2><p><a href='/admin'>Return to Admin Panel</a></p>")
                
            # Prevent deleting the admin user
            if user_email == settings.ADMIN_EMAIL:
                return HTMLResponse("<h2>Error: Cannot delete admin user.</h2><p><a href='/admin'>Return to Admin Panel</a></p>")
                
            # Remove all user data
            db.query(Favorite).filter(Favorite.user_email == user_email).delete()
            db.query(UserBookCategory).filter(UserBookCategory.user_email == user_email).delete()
            db.query(UserArxivTopic).filter(UserArxivTopic.user_email == user_email).delete()
            db.query(User).filter(User.email == user_email).delete()
            db.commit()
            
        # Invalidate cache for this user
        feed_cache.invalidate(user_email=user_email)
        return RedirectResponse(url="/admin", status_code=303)
    except Exception as e:
        logging.error(f"Error deleting user {user_email}: {e}")
        return HTMLResponse(
            f"<h2>Error deleting user.</h2><p>Error: {str(e)}</p><p><a href='/admin'>Return to Admin Panel</a></p>"
        )

@app.get("/select-books", response_class=HTMLResponse)
async def select_books_get(request: Request, user: str = Depends(get_current_user)):
    return templates.TemplateResponse("select_books.html", {"request": request, "book_categories": BOOK_CATEGORIES})

@app.post("/select-books")
async def select_books_post(request: Request, user: str = Depends(get_current_user)):
    form = await request.form()
    books = form.getlist("books")
    if not books:
        return templates.TemplateResponse(
            "select_books.html",
            {"request": request, "book_categories": BOOK_CATEGORIES, "error": "Please select at least one book category."}
        )
    
    with get_db_session() as db:
        # Use the helper method to update user's book categories
        UserBookCategory.add_categories_for_user(db, user, books)
        
    feed_cache.invalidate(user_email=user)
    return RedirectResponse(url="/select-research", status_code=303)

@app.get("/select-research", response_class=HTMLResponse)
async def select_research_get(request: Request, user: str = Depends(get_current_user)):
    return templates.TemplateResponse("select_research.html", {"request": request, "research_categories": ARXIV_TAXONOMY})

@app.post("/select-research")
async def select_research_post(request: Request, user: str = Depends(get_current_user)):
    form = await request.form()
    arxiv = form.getlist("arxiv")
    if not arxiv:
        return templates.TemplateResponse(
            "select_research.html",
            {"request": request, "research_categories": ARXIV_TAXONOMY, "error": "Please select at least one research category."}
        )
    with get_db_session() as db:
        # Use the helper method to update user's arxiv topics
        UserArxivTopic.add_topics_for_user(db, user, arxiv)
    feed_cache.invalidate(user_email=user)
    return RedirectResponse(url="/home", status_code=303)

@app.get("/home", response_class=HTMLResponse)
async def homepage(request: Request, user: str = Depends(get_current_user)):
    with get_db_session() as db:
        user_obj = db.query(User).filter(User.email == user).first()
        book_cats = [category.book_category_id for category in user_obj.book_categories]
        arxiv_cats = [topic.arxiv_topic_id for topic in user_obj.arxiv_topics]
        favs = user_obj.favorites
        favs_data = [
            {
                "id": fav.id,
                "title": fav.title,
                "type": fav.type,
                "link": fav.link,
                "date_published": fav.date_published
            }
            for fav in favs
        ]
        fav_dict = {f"{fav['link']}_{fav['title']}": fav['id'] for fav in favs_data}
    feed_items = await feed_cache.get_feeds(user, book_cats, arxiv_cats)
    for item in feed_items:
        item_key = f"{item['link']}_{item['title']}"
        if item_key in fav_dict:
            item['is_favorite'] = True
            item['favorite_id'] = fav_dict[item_key]
        else:
            item['is_favorite'] = False
    return templates.TemplateResponse("rss_feed.html", {
        "request": request,
        "feed_items": feed_items,
        "user": user_obj,
        "book_categories": book_cats,
        "arxiv_topics": arxiv_cats,
        "favourites": favs_data,
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })

@app.get("/books", response_class=HTMLResponse)
async def books_feed(request: Request, user: str = Depends(get_current_user)):
    with get_db_session() as db:
        user_obj = db.query(User).filter(User.email == user).first()
        book_cats = [category.book_category_id for category in user_obj.book_categories]
        favs = user_obj.favorites
        favs_data = [
            {
                "id": fav.id,
                "title": fav.title,
                "type": fav.type,
                "link": fav.link,
                "date_published": fav.date_published
            }
            for fav in favs
        ]
        fav_dict = {f"{fav['link']}_{fav['title']}": fav['id'] for fav in favs_data}
    feed_items = await feed_cache.get_feeds(user, book_cats, [])
    book_items = [item for item in feed_items if item['type'] == 'book']
    for item in book_items:
        item_key = f"{item['link']}_{item['title']}"
        if item_key in fav_dict:
            item['is_favorite'] = True
            item['favorite_id'] = fav_dict[item_key]
        else:
            item['is_favorite'] = False
    return templates.TemplateResponse("books_feed.html", {
        "request": request,
        "feed_items": book_items,
        "user": user_obj,
        "favourites": favs_data,
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })

@app.get("/research", response_class=HTMLResponse)
async def research_feed(request: Request, user: str = Depends(get_current_user)):
    with get_db_session() as db:
        user_obj = db.query(User).filter(User.email == user).first()
        arxiv_cats = [topic.arxiv_topic_id for topic in user_obj.arxiv_topics]
        favs = user_obj.favorites
        favs_data = [
            {
                "id": fav.id,
                "title": fav.title,
                "type": fav.type,
                "link": fav.link,
                "date_published": fav.date_published
            }
            for fav in favs
        ]
        fav_dict = {f"{fav['link']}_{fav['title']}": fav['id'] for fav in favs_data}
    feed_items = await feed_cache.get_feeds(user, [], arxiv_cats)
    research_items = [item for item in feed_items if item['type'] == 'arxiv']
    for item in research_items:
        item_key = f"{item['link']}_{item['title']}"
        if item_key in fav_dict:
            item['is_favorite'] = True
            item['favorite_id'] = fav_dict[item_key]
        else:
            item['is_favorite'] = False
    return templates.TemplateResponse("research_feed.html", {
        "request": request,
        "feed_items": research_items,
        "user": user_obj,
        "favourites": favs_data,
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })

@app.get("/favourites", response_class=HTMLResponse)
async def favourites_page(request: Request, user: str = Depends(get_current_user)):
    with get_db_session() as db:
        user_obj = db.query(User).filter(User.email == user).first()
        favs = user_obj.favorites
        feed_items = [
            {
                "id": fav.id,
                "title": fav.title,
                "type": fav.type,
                "link": fav.link,
                "published": fav.date_published,  # Changed key to match expected format
                "is_favorite": True,
                "category": fav.type.capitalize()  # Added category field
            }
            for fav in favs
        ]
    return templates.TemplateResponse("favourites.html", {
        "request": request,
        "feed_items": feed_items,  # Changed key from favourites to feed_items
        "favourites": feed_items,  # Keep this for backward compatibility
        "user": user_obj,
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })

@app.post("/favourite")
async def add_favourite(request: Request, title: str = Form(...), type: str = Form(...), link: str = Form(...), date_published: str = Form(...), user: str = Depends(get_current_user)):
    import uuid
    from urllib.parse import unquote
      # URL decode the parameters if needed
    title = unquote(title)
    link = unquote(link)
    date_published = unquote(date_published)
    
    with get_db_session() as db:
        # Check if this item is already in favorites using ORM
        existing = db.query(Favorite).filter(
            (Favorite.user_email == user) & 
            (Favorite.title == title) & 
            (Favorite.link == link)
        ).first()
        
        if existing:
            return {"status": "exists", "id": existing.id}
        
        # Use the helper method to add a favorite
        fav = Favorite.add_favorite(
            db,
            user_email=user,
            title=title,
            type_=type,  # <-- FIXED: use type_ instead of type
            link=link,
            date_published=date_published
        )
        return {"status": "ok", "id": fav.id}

@app.post("/unfavourite")
async def remove_favourite(request: Request, fav_id: str = Form(...), user: str = Depends(get_current_user)):
    with get_db_session() as db:
        # Use the helper method to remove a favorite
        Favorite.remove_favorite(db, fav_id, user)
    return {"status": "ok"}

# =====================
# API Endpoints
# =====================
@app.get("/api/refresh-feeds")
async def refresh_feeds(request: Request, user: str = Depends(get_current_user)):
    # Invalidate the cache for this user to force a refresh
    feed_cache.invalidate(user_email=user)
    
    with get_db_session() as db:
        # Fetch user and related data using ORM relationships
        user_obj = db.query(User).filter(User.email == user).first()
        
        # Extract book categories and arxiv topics
        book_cats = [category.book_category_id for category in user_obj.book_categories]
        arxiv_cats = [topic.arxiv_topic_id for topic in user_obj.arxiv_topics]
        
        # Get favorites and create lookup dict
        fav_dict = {f"{fav.link}_{fav.title}": fav.id for fav in user_obj.favorites}
    
    # Get fresh feeds
    feed_items = await feed_cache.get_feeds(user, book_cats, arxiv_cats)
    
    # Mark items that are in favorites
    for item in feed_items:
        item_key = f"{item['link']}_{item['title']}"
        if item_key in fav_dict:
            item['is_favorite'] = True
            item['favorite_id'] = fav_dict[item_key]
        else:
            item['is_favorite'] = False
    
    return JSONResponse(content={
        "feed_items": feed_items,
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })

# =====================
# View Tracking for Analytics
# =====================
@app.post("/track-view")
async def track_view(request: Request, url: str = Form(...), title: str = Form(...), type: str = Form(...), user: str = Depends(get_current_user)):
    """
    Track when a user views a feed item - this can be used for analytics
    and personalized recommendations in the future
    """
    try:
        # For now, just log the view
        logging.info(f"User {user} viewed {type} item: {title} ({url})")
        return {"status": "ok"}
    except Exception as e:
        logging.error(f"Error tracking view: {str(e)}")
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)