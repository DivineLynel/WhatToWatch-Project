import os
import hmac
import secrets

from flask import Flask, abort, redirect, render_template, request, session, url_for
from dotenv import load_dotenv
from requests import RequestException

from backend.account_logic import (
    create_user,
    get_title_actions,
    get_user_actions,
    get_user_by_email,
    get_user_by_id,
    init_database,
    password_is_valid,
    save_title_action,
)
from backend.search_logic import (
    discover_movies,
    get_movie_genres,
    get_title_details,
    search_movies,
)

load_dotenv()

app = Flask(__name__, template_folder='templates', static_folder='static')
secret_key = os.getenv('FLASK_SECRET_KEY')
if not secret_key or secret_key.startswith('replace-with-') or secret_key.startswith('generate-'):
    raise RuntimeError('FLASK_SECRET_KEY must be configured before starting the app')
app.secret_key = secret_key
app.config.update(
    MAX_CONTENT_LENGTH=2 * 1024 * 1024,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=os.getenv('COOKIE_SECURE', 'true').lower() == 'true',
)
init_database()


@app.context_processor
def security_context():
    token = session.get('csrf_token')
    if not token:
        token = secrets.token_urlsafe(32)
        session['csrf_token'] = token
    return {'csrf_token': token}


@app.before_request
def protect_post_requests():
    if request.method == 'POST':
        supplied_token = request.form.get('csrf_token', '')
        session_token = session.get('csrf_token', '')
        if not session_token or not hmac.compare_digest(supplied_token, session_token):
            abort(400, description='Invalid security token')


@app.after_request
def add_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Content-Security-Policy'] = "default-src 'self' https:; img-src 'self' https: data:; style-src 'self' 'unsafe-inline'; form-action 'self'"
    return response


def signed_in_user():
    user_id = session.get('user_id')
    return get_user_by_id(user_id) if user_id else None

@app.route('/')
def home():
    try:
        genres = get_movie_genres()
    except (RequestException, RuntimeError) as error:
        app.logger.error('TMDB genre request failed: %s', error)
        genres = []
    return render_template('index.html', genres=genres, current_user=signed_in_user())


@app.route('/account')
def account():
    user = signed_in_user()
    if not user:
        return redirect(url_for('login'))
    return render_template('account.html', user=user, actions=get_user_actions(user['id']))


@app.route('/register', methods=['GET', 'POST'])
def register():
    if signed_in_user():
        return redirect(url_for('account'))
    error = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        if not username or len(username) > 80 or '@' not in email or len(password) < 8:
            error = 'Enter a username, valid email, and password of at least 8 characters.'
        elif create_user(username, email, password) is None:
            error = 'That email is already registered.'
        else:
            user = get_user_by_email(email)
            session['user_id'] = user['id']
            return redirect(url_for('account'))
    return render_template('register.html', error=error)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if signed_in_user():
        return redirect(url_for('account'))
    error = None
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        user = get_user_by_email(email)
        if not password_is_valid(user, password):
            error = 'Email or password is incorrect.'
        else:
            session['user_id'] = user['id']
            return redirect(url_for('account'))
    return render_template('login.html', error=error)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))


@app.route('/catalog')
def catalog():
    genre_id = request.args.get('genre', type=int)
    page = max(request.args.get('page', 1, type=int), 1)
    try:
        genres = get_movie_genres()
        selected_genre = next((genre for genre in genres if genre['id'] == genre_id), None)
        movies = discover_movies(genre_id, page) if selected_genre else None
    except (RequestException, RuntimeError) as error:
        app.logger.error('TMDB catalog request failed: %s', error)
        return render_template(
            'catalog.html',
            genres=[],
            error='The catalog is unavailable.',
            current_user=signed_in_user(),
        ), 502

    return render_template(
        'catalog.html',
        genres=genres,
        movies=movies,
        selected_genre=selected_genre,
        current_user=signed_in_user(),
    )


@app.route('/search', methods=['POST'])
def search():
    query = request.form.get('search_movie', '').strip()
    if not query:
        return render_template('index.html', error='Enter a title to search.', current_user=signed_in_user())

    try:
        results = search_movies(query)
    except (RequestException, RuntimeError) as error:
        app.logger.error('TMDB search failed: %s', error)
        return render_template(
            'index.html',
            error='The movie service is unavailable. Check your API configuration.',
            current_user=signed_in_user(),
        ), 502

    return render_template('index.html', results=results, query=query, current_user=signed_in_user())


@app.route('/details/<media_type>/<int:item_id>')
def details(media_type, item_id):
    try:
        title = get_title_details(media_type, item_id)
    except (RequestException, RuntimeError, ValueError) as error:
        app.logger.error('TMDB details request failed: %s', error)
        return render_template('index.html', error='That movie or series could not be loaded.'), 404

    user = signed_in_user()
    actions = get_title_actions(user['id'], media_type, item_id) if user else set()
    return render_template('details.html', title=title, current_user=user, actions=actions)


@app.route('/details/<media_type>/<int:item_id>/action', methods=['POST'])
def title_action(media_type, item_id):
    user = signed_in_user()
    if not user:
        return redirect(url_for('login'))
    if media_type not in {'movie', 'tv'}:
        return 'Unsupported title type', 400
    action = request.form.get('action', '')
    title = request.form.get('title', 'Untitled')
    poster_path = request.form.get('poster_path') or None
    try:
        save_title_action(user['id'], media_type, item_id, title, poster_path, action)
    except ValueError:
        return 'Unsupported title action', 400
    return redirect(url_for('details', media_type=media_type, item_id=item_id))

if __name__ == '__main__':
    app.run(
        debug=os.getenv('FLASK_DEBUG', 'false').lower() == 'true',
        host=os.getenv('FLASK_HOST', '127.0.0.1'),
        port=int(os.getenv('PORT', '5000')),
    )
