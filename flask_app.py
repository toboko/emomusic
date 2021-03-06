import base64
import json
import os
import numpy as np
import requests
import time
from flask import Flask, redirect, render_template, request, url_for, session

try:
    from urllib import quote  # Python 2.X
except ImportError:
    from urllib.parse import quote  # Python 3+

# azure env vars
api_key_azure = os.environ['AZURE_APIKEY']
uri_azure = os.environ['AZURE_URI']
def USING_AZURE():
    return True

# default playlist
playlist_id_default = "2pHddKK7ZpHu6YUVNkZEWr"

# spotify env vars
client_id_spotify = os.environ['SPOTIFY_ID']
redirect_uri_spotify = 'http://localhost:5000/callback'
state_spotify = 'lakdo'
scopes_spotify = 'user-read-playback-state user-modify-playback-state playlist-read-private playlist-read-collaborative'

# spotify auth url
auth_url = 'https://accounts.spotify.com/authorize'
auth_url += '?response_type=token'
auth_url += '&client_id=' + quote(client_id_spotify)
auth_url += '&scope=' + quote(scopes_spotify)
auth_url += '&redirect_uri=' + quote(redirect_uri_spotify, safe='')
auth_url += '&state=' + quote(state_spotify)

# flask server run
app = Flask(__name__)
app.secret_key = os.environ['SESSION_SECRET']
app.debug = True


@app.route("/", methods=["GET", "POST"])
def index():
    if (request.method == "GET"):
        # render template
        return render_template("main.html", url=auth_url)

    return redirect(url_for('index'))


# callback for spotify login
@app.route("/callback", methods=["GET"])
def callback():
    if (request.method == "GET"):
        # render template
        return render_template("callback.html")


# return chords progression in midi format
@app.route("/emotion", methods=["POST"])
def emotion():
    if (request.method == "POST"):
        # check request value
        if not request.values.get('token'):
            return json.dumps({
                'success': False,
                'message': 'Token Expired! Refresh your Token'
            }), 500, {'ContentType': 'application/json'}
        if not request.values.get('photo'):
            return json.dumps({
                'success': False,
                'message': 'Error on getting your image. We need to see you'
            }), 500, {'ContentType': 'application/json'}
        # store token
        session['token'] = request.values.get('token')
        # get picture
        photo_base64 = request.values.get("photo")
        # remove base64 header
        photo_base64 = photo_base64[23:]
        # convert to bytes
        photo_byte = base64.b64decode(photo_base64)

        # get device
        device = get_device()
        # check active device
        if device is not None:
            if USING_AZURE():
                # assert required values
                assert uri_azure, api_key_azure
                assert photo_byte
                # headers parameters
                headers = {
                    'Content-Type': 'application/octet-stream',
                    'Ocp-Apim-Subscription-Key': api_key_azure
                }
                # post parameters
                params = {
                    'returnFaceId': 'true',
                    'returnFaceLandmarks': 'false',
                    'returnFaceAttributes': 'emotion',
                }
                # get response from azure
                response = requests.post(uri_azure, params=params, headers=headers, data=photo_byte)
                response_json = response.json()
                # check azure response and understand emotion
                try:
                    response_json[0]
                    # save smile and emotions results
                    emotions = response_json[0]['faceAttributes']['emotion']
                except IndexError:
                    # handle this
                    return json.dumps({
                        'success': False,
                        'message': 'Error on recognizing emotion'
                    }), 500, {'ContentType': 'application/json'}
            else:
                emotions = random_emotions()

            # selection of the main emotion
            emo = pick_max_emo(emotions)
            # get tracks descriptors of user
            tracks_descriptors = get_tracks()

            if tracks_descriptors is not None:

                # get chosen track
                chosen = choose_track(emo, tracks_descriptors)
                if chosen is not None:

                    # play track
                    if play_track(chosen['uri'], device):
                        return json.dumps({
                            'success': True,
                            'emotion': emo,
                            'audio_features': chosen
                        }), 200, {'ContentType': 'application/json'}
                    else:
                        return json.dumps({
                            'success': False,
                            'message': "Error during playback. Probably you need a Spotify Premium Account"
                        }), 500, {'ContentType': 'application/json'}
                else:
                    return json.dumps({
                        'success': False,
                        'message': "Track not found for current emotion"
                    }), 500, {'ContentType': 'application/json'}
            else:
                return json.dumps({
                    'success': False,
                    'message': "Error on getting tracks"
                }), 500, {'ContentType': 'application/json'}
        else:
            return json.dumps({
                'success': False,
                'message': 'No active device available. Plese open you Spotify App'
            }), 500, {'ContentType': 'application/json'}

# https://developer.spotify.com/console/get-users-available-devices/#
# GET METHOD : https://api.spotify.com/v1/me/player/devices
# SCOPE : user-read-playback-state
# RESPONSE :
#     {   "devices": [
#         {
#           "id": "********",
#           "is_active": true,
#           "is_private_session": false,
#           "is_restricted": false,
#             ...
#         }, {
#           "id": "********",
#           "is_active": false,
#             ...
#         } ]
#     }
def get_device():
    headers = {"Authorization": "Bearer %s" % session['token']}
    # search active devices
    # create request
    response = requests.get(headers=headers, url="https://api.spotify.com/v1/me/player/devices")
    # check required values
    if not response.status_code == 200:
        return None
    response = response.json()
    # for each playlist extract track id
    if len(response['devices']) > 0:
        for device in response['devices']:
            if device['type'] == 'Computer':
                return device

        return response['devices'][0]
    else:
        return None


# FOR SOLE PREMIUM ACCOUNTS!
# https://developer.spotify.com/documentation/web-api/reference/player/start-a-users-playback/
# PUT METHOD : https://api.spotify.com/v1/me/player/play
# SCOPE : user-modify-playback-state
# REQUEST :
#     body-parameters: {"uris": ["spotify:track:4iV5W9uYEdYUVa79Axb7Rh"]}
def play_track(uri_track, device):
    headers = {"Authorization": "Bearer %s" % session['token']}
    params = {'uris': [str(uri_track)]}
    # create request
    response = requests.put(headers=headers, data=json.dumps(params), url="https://api.spotify.com/v1/me/player/play?device_id=" + str(device['id']))
    # check required values
    if not response.status_code == 204:
        return False
    return True

# FOR SOLE PREMIUM ACCOUNTS!
# https://developer.spotify.com/documentation/web-api/reference/player/pause-a-users-playback/
# PUT METHOD : https://api.spotify.com/v1/me/player/pause
# SCOPE : user-modify-playback-state
@app.route("/pause", methods=["POST"])
def pause():
    if (request.method == "POST"):
        # check request value
        if not request.values.get('token'):
            return json.dumps({
                'success': False,
                'message': 'Token Expired! Refresh your Token'
            }), 500, {'ContentType': 'application/json'}
        # store token
        session['token'] = request.values.get('token')
        # get device
        device = get_device()
        # check active device
        if device is not None:
            headers = {"Authorization": "Bearer %s" % session['token']}
            # create request
            response = requests.put(headers=headers, url="https://api.spotify.com/v1/me/player/pause?device_id=" + str(device['id']))
            # check required values
            if not response.status_code == 204:
                return json.dumps({
                    'success': False,
                    'message': 'You need a Spotify Premium Account'
                }), 500, {'ContentType': 'application/json'}
            return json.dumps({
                'success': True,
            }), 200, {'ContentType': 'application/json'}
        else:
            return json.dumps({
                'success': False,
                'message': 'No active device available pause music'
            }), 500, {'ContentType': 'application/json'}

# FOR SOLE PREMIUM ACCOUNTS!
# https://developer.spotify.com/documentation/web-api/reference/player/start-a-users-playback/
# PUT METHOD : https://api.spotify.com/v1/me/player/play
# SCOPE : user-modify-playback-state
@app.route("/play", methods=["POST"])
def play():
    if (request.method == "POST"):
        # check request value
        if not request.values.get('token'):
            return json.dumps({
                'success': False,
                'message': 'Token Expired! Refresh your Token'
            }), 500, {'ContentType': 'application/json'}
        # store token
        session['token'] = request.values.get('token')
        # get device
        device = get_device()
        # check active device
        if device is not None:
            headers = {"Authorization": "Bearer %s" % session['token']}
            # create request
            response = requests.put(headers=headers, url="https://api.spotify.com/v1/me/player/play?device_id=" + str(device['id']))
            # check required values
            if not response.status_code == 204:
                return json.dumps({
                    'success': False,
                    'message': 'You need a Spotify Premium Account'
                }), 500, {'ContentType': 'application/json'}
            return json.dumps({
                'success': True,
            }), 200, {'ContentType': 'application/json'}
        else:
            return json.dumps({
                'success': False,
                'message': 'No active device available playing music'
            }), 500, {'ContentType': 'application/json'}


def get_tracks():
    headers = {"Authorization": "Bearer %s" % session['token']}
    # search music feature inside user's playlists
    # create request
    response = requests.get(headers=headers, url="https://api.spotify.com/v1/me/playlists")
    # check required values
    if not response.status_code == 200:
        return None
    else:
        answer = response.json()
        # collect playlists
        playlist_links = []
        # for each playlist extract playlist reference
        for playlist in answer['items']:
            tracks = playlist['tracks']
            if (tracks['total'] > 0):  # exclusion of empty playlists
                playlist_links.append(tracks['href'])  # links are already unique
        # collect tracks
        track_ids = []

        if True:
            response = requests.get(headers=headers, url="https://api.spotify.com/v1/playlists/" + playlist_id_default)
            # check required values
            if not response.status_code == 200:
                return None
            for track in response.json()['tracks']['items']:
                track_ids.append(track['track']['id'])
        else:
            # for each playlist, retrieve the ids of all the songs contained in it
            params = {'fields': 'items(track(id))'}
            for playlist_link in playlist_links:
                response = requests.get(headers=headers, url=playlist_link, params=params)
                # check required values
                if not response.status_code == 200:
                    return None
                for track in response.json()['items']:
                    track_ids.append(track['track']['id'])
                time.sleep(0.005)  # delay among each playlist request
        # truncate track_ids quantity to maximum value (100)
        track_ids = np.unique(track_ids)
        np.random.shuffle(track_ids)
        if (len(track_ids) > 100):
            track_ids = track_ids[0:99]
        # convert track_ids to string
        track_ids_str = np.array2string(track_ids, separator=',').translate({ord(i): None for i in "[] '\n"})
        # create request
        params = {'ids': track_ids_str}
        response = requests.get(headers=headers, url='https://api.spotify.com/v1/audio-features', params=params)
        # check required values
        if not response.status_code == 200:
            return None
        # tracks information
        tracks_descriptors = response.json()['audio_features']
        return tracks_descriptors


# input-structures
#       tracks : [{                       emotions : {
#           "energy": float,                    "anger": float,
#           "tempo": float,                     "contempt": float,
#           "loudness": float,                  "disgust": float,
#           "mode": 0|1,                        "fear": float,
#           "speechiness": float,               "happiness": float,
#           "acousticness": float,              "neutral": float,
#           "instrumentalness": float,          "sadness": float,
#           "liveness": float,                  "surprise": float
#           "valence": float,              }
#           "uri": String,
#           ...
#           } , {
#           ...
#           }
#       ]
def choose_track(emo, tracks_descriptors):
    # mode [0|1], valence [0,1], tempo [bpm], energy [0,1], danceability [0,1] - filtering
    tb_filtered = tracks_descriptors.copy()

    # emo dependent predicative constraint definition for filtering
    if (emo != 'neutral'):
        if (emo == 'anger' or emo == 'disgust' or emo == 'contempt'): # fast saw, red
            criteria = lambda t : (t['valence'] < 0.4 and
                                   t['mode'] == 0 and
                                   t['tempo'] > 110 and t['tempo'] < 170 and
                                   t['energy'] > 0.7)
        elif (emo == 'fear'): # slow saw, blue
            criteria = lambda t : (t['valence'] < 0.4 and
                                   t['mode'] == 0 and
                                   t['tempo'] > 80 and t['tempo'] < 110 and
                                   t['energy'] > 0.7)
        elif (emo == 'sadness'): # slow sine, blue
            criteria = lambda t : (t['valence'] < 0.4 and
                                   t['mode'] == 0 and
                                   t['tempo'] > 80 and t['tempo'] < 110 and
                                   t['energy'] < 0.7)
        elif (emo == 'happiness' or emo == 'surprise'): # fast sine, yellow
            criteria = lambda t : (t['valence'] > 0.6 and t['mode'] == 1 and
                                   t['tempo'] > 100 and t['tempo'] < 150 and
                                   t['energy'] > 0.6 and
                                   t['danceability'] > 0.6)
        tb_filtered = [t for t in tb_filtered if (criteria(t))]

    if (len(tb_filtered) > 0):
        chosen = np.random.choice(tb_filtered)
        return chosen
    else:
        print('No track found, please adjust the implementation/thresholds or enlarge your playlist =)')

def random_emotions():
    ret = {'anger': 0, 'contempt': 0, 'disgust': 0, 'fear': 0, 'happiness': 0,
           'neutral': 0, 'sadness': 0, 'surprise': 0}
    ret[np.random.choice(list(ret.keys()))] = 1
    return ret

def pick_max_emo(emotions):
    pick = list(emotions.keys())[np.argmax(list(emotions.values()))]
    # we are always neutral so try to avoid cyclic situation
    if str(pick) in ('neutral') and emotions['neutral'] > 0.9:
        del emotions['neutral']
        pick = list(emotions.keys())[np.argmax(list(emotions.values()))]
    return pick
