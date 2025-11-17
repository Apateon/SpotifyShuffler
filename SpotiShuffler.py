import os
import random
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, session, url_for
from flask_sqlalchemy import SQLAlchemy

from spotipy import Spotify
from spotipy.oauth2 import SpotifyOAuth
from spotipy.cache_handler import FlaskSessionCacheHandler

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv("SECRET_KEY")

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///spotifyshuffler.db'
db = SQLAlchemy(app)

class ShufflerUser(db.Model):
    id = db.Column(db.String(50), primary_key=True)
    display_name = db.Column(db.String(30), nullable=False)
    personal_cooldown_time = db.Column(db.Integer)
    average_times_played = db.Column(db.Integer)
    last_played_song_id = db.Column(db.Integer)
    shuffle_songs_after = db.Column(db.Integer)

    def whatareyou(self):
        return f'I am user: {self.id} with name {self.display_name}'

class SongHistory(db.Model):
    song_id = db.Column(db.String(30), primary_key=True)
    user_id = db.Column(db.String(50), db.ForeignKey('shuffler_user.id'))
    played_times = db.Column(db.Integer)
    last_played = db.Column(db.DateTime)

    def __repr__(self):
        return f'Song ID: {self.song_id} played {self.played_times} times, last played on {self.last_played}'

s_client_id = os.getenv("CLIENT_ID")
s_client_secret = os.getenv("CLIENT_SECRET")

s_redirect_uri = 'http://127.0.0.1:8000/callback'
s_scope = 'playlist-read-private'

s_cache_handler = FlaskSessionCacheHandler(session)
sp_oauth = SpotifyOAuth(
    client_id = s_client_id,
    client_secret = s_client_secret,
    redirect_uri = s_redirect_uri,
    scope=s_scope,
    cache_handler=s_cache_handler,
    show_dialog=True
    )

sp = Spotify(auth_manager=sp_oauth)

def check_token():
    if not sp_oauth.validate_token(s_cache_handler.get_cached_token()):
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
        user_average = total_played / len(all_played)
        user = db.session.get(ShufflerUser, user_id)
        user.average_times_played = user_average
        try:
            db.session.commit()
        except:
            return 'There was an issue updating user average'

def shuffle_songs():
    return 'Shuffling Songs'

def update_history():
    return 'Updating History'

@app.route('/')
def index():
    if(check_token() is not True):
        return render_template('index.html')
    else:
        user = sp.current_user()
        #check if the user is already in the database
        something = ""
        user_in_db = db.session.get(ShufflerUser, user['id'])
        if user_in_db is None:
            #commit the user to the database
            new_user = ShufflerUser(id = user['id'], display_name = user['display_name'])
            new_user.personal_cooldown_time = 0
            new_user.average_times_played = 0
            new_user.last_played_song_id = ""
            new_user.shuffle_songs_after = 0

            try:
                db.session.add(new_user)
                db.session.commit()
            except:
                return 'There was an issue adding the user'
            something = "New user added!"
        else:
            something = user_in_db.whatareyou()
        #get the user playlists
        playlists = sp.current_user_playlists()
        playlists_info = [(pl['name'], pl['tracks'], pl['id']) for pl in playlists['items']]
        return render_template('index.html', 
                               user_name=sp.current_user()['display_name'],
                               playlists=playlists_info,
                               toprint = something)

@app.route('/login')    
def login():
    if check_token() is not True:
        return check_token()
    return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/callback')
def callback():
    sp_oauth.get_access_token(request.args['code'])
    return redirect(url_for('index'))

@app.route('/updatesongs', methods=['GET', 'POST'])
def updatesongs():
    if request.method == 'POST':
        current_user_id = sp.current_user()['id']
        songset = set()
        
        #get playlist selected by the user
        playlists = request.form.getlist('playlists')

        #get songs from selected playlists
        for playlist in playlists:
            result = sp.playlist_items(playlist, fields="next,items.track.id")

            while result:
                for item in result.get('items',[]):
                    if item and item.get('track') and item['track'].get('id'):
                        songset.add(item['track']['id'])
                result = sp.next(result)

        #get existing songs from the database
        existing_songs = db.session.execute(
            db.select(SongHistory.song_id).filter(SongHistory.user_id == current_user_id)
            ).scalars().all()

        #removing songs not in playlist
        id_to_remove = set(existing_songs) - songset
        if id_to_remove:
            db.session.execute(
                db.delete(SongHistory)
                .filter(SongHistory.user_id == current_user_id)
                .filter(SongHistory.song_id.in_(id_to_remove))
            )
            try:
                db.session.commit()
            except:
                return 'There was an issue removing old songs from history'

        #adding new songs
        new_songs = []
        for song_id in songset:
            if song_id not in existing_songs:
                new_songs.append(SongHistory(
                    song_id = song_id,
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

        update_average_played_times(current_user_id)        
        
        #tracks_in_db = db.session.execute(
        #    db.select(SongHistory).filter(SongHistory.user_id == current_user_id)
        #    ).scalars().all()

        #random_songs = random.sample(playlist_items, 500)
        songs = '<br>'.join(f'{item}' for item in songset)

        return songs
    
    return 'Nothing'

if __name__ == "__main__":
    app.run(debug=True, port=8000)