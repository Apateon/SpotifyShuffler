import os
import random
import time
from dotenv import load_dotenv
from datetime import datetime

from sqlalchemy import func
from flask import Flask, render_template, request, redirect, session, url_for
from flask_sqlalchemy import SQLAlchemy

from spotipy import Spotify
from spotipy.oauth2 import SpotifyOAuth, SpotifyOauthError
from spotipy.cache_handler import FlaskSessionCacheHandler, CacheFileHandler

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv("SECRET_KEY")

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///spotifyshuffler.db'
db = SQLAlchemy(app)

app.config['SCHEDULER_API_ENABLED'] = True
app.config['SHEDULER_TIMEZONE'] = 'UTC'

#User Table
class ShufflerUser(db.Model):
    id = db.Column(db.String(50), primary_key=True)
    display_name = db.Column(db.String(30), nullable=False)
    average_times_played = db.Column(db.Integer)
    last_played_song_id = db.Column(db.String(12))
    selected_playlists = db.Column(db.Text)

#Song History Table
class SongHistory(db.Model):
    isrc = db.Column(db.String(12), primary_key=True)
    song_id = db.Column(db.String(30))
    user_id = db.Column(db.String(50), db.ForeignKey('shuffler_user.id'))
    played_times = db.Column(db.Integer)
    last_played = db.Column(db.DateTime)

s_client_id = os.getenv("CLIENT_ID")
s_client_secret = os.getenv("CLIENT_SECRET")

s_redirect_uri = 'http://127.0.0.1:8000/callback'
s_scope = 'playlist-read-private user-read-recently-played user-modify-playback-state'

web_cache_handler = FlaskSessionCacheHandler(session)
sp_oauth = SpotifyOAuth(
    client_id = s_client_id,
    client_secret = s_client_secret,
    redirect_uri = s_redirect_uri,
    scope=s_scope,
    cache_handler = web_cache_handler,
    show_dialog = True
)

sp = Spotify(auth_manager=sp_oauth)

background_cache_handler = CacheFileHandler(cache_path=".spotify_token_cache.json")

def get_background_sp_client():
    background_sp_oauth = SpotifyOAuth(
        client_id = s_client_id,
        client_secret = s_client_secret,
        redirect_uri = s_redirect_uri,
        scope = s_scope,
        cache_handler = background_cache_handler
    )
    token_info = background_cache_handler.get_cached_token()
    if token_info and background_sp_oauth.validate_token(token_info):
        return Spotify(auth_manager=background_sp_oauth)
    else:
        print("Error: Background job token is invalid. User must log in again.")
        return None

def check_token():
    if not sp_oauth.validate_token(web_cache_handler.get_cached_token()):
        auth_url = sp_oauth.get_authorize_url()
        return redirect(auth_url)
    return True

#calculate new average and update in user table
def update_average_played_times(user_id):
        all_played = db.session.execute(
            db.select(SongHistory.played_times).filter(SongHistory.user_id == user_id)
            ).scalars().all()
        total_played = 0
        if all_played:
            for times in all_played:
                total_played += times
        user_average = int(total_played / len(all_played))
        user = db.session.get(ShufflerUser, user_id)
        user.average_times_played = user_average
        try:
            db.session.commit()
        except:
            return 'There was an issue updating user average'
        return user_average

#update the song history table with the songs that have been played
def update_history(user_id, sp_client):
    recently_played = sp_client.current_user_recently_played()['items']
    last_song = db.session.execute(db.select(ShufflerUser.last_played_song_id)).scalars().first()
    for song in recently_played:
        if song['track']['external_ids']['isrc'] == last_song:
            break
        else:
            song_in_history = db.session.get(SongHistory, song['track']['external_ids']['isrc'])
            if song_in_history:
                song_in_history.played_times += 1
                song_in_history.last_played = datetime.strptime(song['played_at'], '%Y-%m-%dT%H:%M:%S.%fZ')

    user = db.session.get(ShufflerUser, user_id)
    user.last_played_song_id = recently_played[0]['track']['external_ids']['isrc']

    try:
        db.session.commit()
    except:
        return 'There was an issue updating song history'
    return 'updating history'

#shuffle songs based on the average times played
def shuffle_songs(user_id, based_on, amount):
    if based_on == 'time':
        amount = int(amount / 3)
    else:
        amount = int(amount)
    
    average_played = update_average_played_times(user_id)
    song_list = db.session.execute(
        db.select(SongHistory.song_id)
        .filter(SongHistory.played_times <= average_played)
        .order_by(func.random())
        .limit(amount)
        ).scalars().all()
    
    if len(song_list) < amount:
        needed = amount - len(song_list)
        more_songs = db.session.execute(
            db.select(SongHistory.song_id)
            .filter(SongHistory.played_times >= average_played)
            .order_by(SongHistory.last_played.asc())
            .limit(needed)
        ).scalars().all()
        song_list.extend(more_songs)

    #shuffle them around and then add them to the queue
    random.shuffle(song_list)

    #add songs to the queue
    for song in song_list:
        sp.add_to_queue(song)

    return len(song_list)

def scheduled_jobs():
    print("Running scheduled job")
    with app.app_context():
        user = db.session.execute(db.select(ShufflerUser)).scalars().first()
        if not user:
            print("No users found in the database")
            return
        
        sp_client = get_background_sp_client()

        if sp_client:
            update_history(user.id, sp_client)
        else:
            print("failed to authenticate")

@app.route('/callback')
def callback():
    try:
        sp_oauth.get_access_token(request.args['code'])
    except SpotifyOauthError:
        return redirect(url_for('index'))

    token_info = web_cache_handler.get_cached_token()
    if token_info:
        background_cache_handler.save_token_to_cache(token_info)
    
    return redirect(url_for('index'))

@app.route('/login')    
def login():
    if check_token() is not True:
        return check_token()
    return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/')
def index():
    if(check_token() is not True):
        return render_template('index.html')
    else:
        message = request.args.get('message')
        message_title = request.args.get('message_title')

        user = sp.current_user()

        #check if the user is already in the database
        if db.session.get(ShufflerUser, user['id']) is None:
            new_user = ShufflerUser(id = user['id'], 
                                    display_name = user['display_name'],
                                    average_times_played = 0,
                                    last_played_song_id = "",
                                    selected_playlists = "")

            try:
                db.session.add(new_user)
                db.session.commit()
            except:
                return 'There was an issue adding the user'
        
        #get the user's playlists
        playlists = sp.current_user_playlists()
        playlists_info = [(pl['name'], pl['tracks'], pl['id']) for pl in playlists['items']]
        
        #get selected playlists
        db_user = db.session.get(ShufflerUser, user['id'])
        selected_playlists = []
        if db_user and db_user.selected_playlists:
            selected_playlists = db_user.selected_playlists.split(',')

        return render_template('index.html', 
                               user_name = sp.current_user()['display_name'],
                               playlists = playlists_info,
                               scheduler_running = scheduler.running,
                               selected_playlists = selected_playlists,
                               message=message,
                               message_title=message_title)

@app.route('/printtable')
def printtable():
    #song history table
    all_songs = db.session.execute(db.select(SongHistory).order_by(SongHistory.last_played.desc())).scalars().all()
    table = '<h2>Song history</h2><table><tr><th>ISRC</th><th>Song ID</th><th>User ID</th><th>Played Times</th><th>Last Played</th></tr>'
    for song in all_songs:
        table += f'<tr><td>{song.isrc}</td><td>{song.song_id}</td><td>{song.user_id}</td><td>{song.played_times}</td><td>{song.last_played}</td></tr>'
    table += '</table>'

    #shuffler user
    all_users = db.session.execute(db.select(ShufflerUser)).scalars().all()
    table += '<h2>Shuffler Users</h2><table><tr><th>ID</th><th>Display Name</th><th>Avg Played</th><th>Last Song ID</th></tr>'
    for user in all_users:
        table += f'<tr><td>{user.id}</td><td>{user.display_name}</td><td>{user.average_times_played}</td><td>{user.last_played_song_id}</td></tr>'
    table += '</table>'
    return table

@app.route('/updatehistory')
def updatehistory():
    if(check_token() is not True):
        return check_token()
    update_history(sp.current_user()['id'], sp)
    return redirect(url_for('index', message="History updated", message_title="Success"))

@app.route('/shuffler', methods=['GET', 'POST'])
def shuffler():
    if(check_token() is not True):
        return check_token()
    if request.method == 'POST':
        based_on = request.form.get('based_on')
        amount = request.form.get('amount') if request.form.get('amount') is not "" else 0
        amount = int(amount)

        if amount < 1:
            return redirect(url_for('index', message="Please enter a valid amount", message_title="Something Went Wrong"))
        
        songsadded = shuffle_songs(sp.current_user()['id'], based_on, amount)
        return redirect(url_for('index', message=f"{songsadded} songs added to queue", message_title="Songs Added to Queue"))
    return redirect(url_for('index'))

@app.route('/updatesongs', methods=['GET', 'POST'])
def updatesongs():
    if request.method == 'POST':
        current_user_id = sp.current_user()['id']
        songset = {}
        
        #get playlist selected by the user
        playlists = request.form.getlist('playlists')

        #update user's selected playlists
        user = db.session.get(ShufflerUser, current_user_id)
        if user:
            user.selected_playlists = ",".join(playlists)
            try:
                db.session.commit()
            except:
                return 'There was an issue updating selected playlists'

        #get songs from selected playlists
        for playlist in playlists:
            result = sp.playlist_items(playlist, fields="next,items.track.id, items.track.external_ids.isrc")

            while result:
                for item in result.get('items',[]):
                    if item and item['track'].get('external_ids') and item['track']['external_ids'].get('isrc'):
                        songset[item['track']['external_ids']['isrc']] = item['track']['id']
                result = sp.next(result)

        #get existing songs from the database
        existing_songs = db.session.execute(
            db.select(SongHistory.isrc).filter(SongHistory.user_id == current_user_id)
            ).scalars().all()

        #removing songs not in playlist
        ids_to_remove = set(existing_songs) - set(songset.keys())
        if ids_to_remove:
            db.session.execute(
                db.delete(SongHistory)
                .filter(SongHistory.user_id == current_user_id)
                .filter(SongHistory.isrc.in_(ids_to_remove))
            )
            try:
                db.session.commit()
            except:
                return 'There was an issue removing old songs from history'

        #adding new songs
        new_songs = []
        for isrc in songset:
            if isrc not in existing_songs:
                new_songs.append(SongHistory(
                    isrc = isrc,
                    song_id = songset[isrc],
                    user_id = current_user_id,
                    played_times = 0,
                    last_played = None
                    )
                )
        if new_songs:
            db.session.add_all(new_songs)
            try:
                db.session.commit()
            except:
                return 'There was an issue adding new songs to history'
    return redirect(url_for('index', message="Playlists updated", message_title="Success"))

if __name__ == "__main__":
    with app.app_context():
        db.create_all()

    app.run(debug=True, port=8000)