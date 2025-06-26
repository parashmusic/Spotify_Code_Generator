import sys
import requests
import os
import webbrowser
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QFileDialog, QMessageBox,
    QListWidget, QListWidgetItem
)
from PyQt5.QtGui import QPixmap, QIcon
from PyQt5.QtCore import Qt, QSize, pyqtSignal, QThread, QTimer
from io import BytesIO
from PIL import Image
import spotipy
from spotipy.oauth2 import SpotifyOAuth

class CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()

        query = urlparse(self.path).query
        params = parse_qs(query)

        if 'code' in params:
            self.server.auth_code = params['code'][0]
            self.wfile.write(b"<h1>Authentication successful!</h1><p>You can close this window.</p>")
        else:
            self.wfile.write(b"<h1>Authentication failed</h1>")

        threading.Thread(target=self.server.shutdown, daemon=True).start()

class SearchWorker(QThread):
    search_complete = pyqtSignal(list)
    auth_needed    = pyqtSignal()

    def __init__(self, query, sp_oauth):
        super().__init__()
        self.query    = query
        self.sp_oauth = sp_oauth

    def run(self):
        try:
            token_info = self.sp_oauth.get_cached_token()
            if not token_info:
                self.auth_needed.emit()
                return

            sp = spotipy.Spotify(auth=token_info['access_token'])
            results = sp.search(q=self.query, type='track', limit=5)
            tracks = []
            for item in results['tracks']['items']:
                tracks.append({
                    'name':   item['name'],
                    'artist': item['artists'][0]['name'],
                    'album':  item['album']['name'],
                    'uri':    item['uri'],
                    'image':  item['album']['images'][0]['url']
                              if item['album']['images'] else None
                })
            self.search_complete.emit(tracks)

        except Exception as e:
            print(f"Search error: {e}")
            self.search_complete.emit([])

class SpotifyCodeGenerator(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Spotify Code Generator")
        self.setWindowIcon(QIcon("spotify_icon.png"))
        self.setFixedSize(600, 700)
        self.setStyleSheet(self.get_stylesheet())

        #OAuth to use 127.0.0.1:8888 
        self.sp_oauth = SpotifyOAuth(
            client_id="Client_ID",
            client_secret="Client_secret",
            redirect_uri="http://127.0.0.1:8888/callback",
            scope="user-library-read",
            cache_handler=spotipy.cache_handler.CacheFileHandler(".spotify_token_cache")
        )

        self.initUI()
        self.check_auth_status() 

    def check_auth_status(self):
        token_info = self.sp_oauth.get_cached_token()
        if not token_info:
            QTimer.singleShot(0, self.authenticate)
        else:
            self.status_bar.setText("Authenticated with Spotify")

    def authenticate(self):
        HTTPServer.allow_reuse_address = True
        server = HTTPServer(('127.0.0.1', 8888), CallbackHandler)
        server.auth_code = None

        threading.Thread(target=server.serve_forever, daemon=True).start()
        webbrowser.open(self.sp_oauth.get_authorize_url())

        while server.auth_code is None:
            QApplication.processEvents()

        try:
            self.sp_oauth.get_access_token(server.auth_code)
            QMessageBox.information(self, "Success", "Authenticated with Spotify!")
            self.status_bar.setText("Authenticated with Spotify")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Authentication failed:\n{e}")
        finally:
            server.server_close()

    def get_stylesheet(self):
        return """
            QMainWindow { background-color: #191414; }
            QLabel       { color: #FFFFFF; font-size: 14px; }
            QLineEdit    { background-color: #282828; color: #FFFFFF; border: 1px solid #535353; border-radius: 4px; padding: 8px; }
            QPushButton  { background-color: #1DB954; color: #FFFFFF; border: none; border-radius: 20px; padding: 10px 20px; }
            QPushButton:hover   { background-color: #1ED760; }
            QPushButton:pressed { background-color: #1AA34A; }
            QPushButton:disabled{ background-color: #535353; color: #B3B3B3; }
            QListWidget  { background-color: #282828; color: #FFFFFF; border: 1px solid #535353; border-radius: 4px; }
            QListWidget::item:hover    { background-color: #383838; }
            QListWidget::item:selected { background-color: #1DB954; }
        """

    def initUI(self):
        c = QWidget(); self.setCentralWidget(c)
        layout = QVBoxLayout(c); layout.setContentsMargins(30,30,30,30); layout.setSpacing(20)

        header = QLabel("Spotify Code Generator")
        header.setStyleSheet("font-size:24px; font-weight:bold; color:#1DB954;")
        header.setAlignment(Qt.AlignCenter)
        layout.addWidget(header)
        layout.addWidget(QLabel("Search for a song:"))
        self.search_input = QLineEdit(placeholderText="Enter song name and artist…")
        search_btn = QPushButton("Search")
        search_btn.clicked.connect(self.search_tracks)
        row = QHBoxLayout(); row.addWidget(self.search_input); row.addWidget(search_btn)
        layout.addLayout(row)


        self.results_list = QListWidget()
        self.results_list.setIconSize(QSize(50, 50))
        self.results_list.itemClicked.connect(self.select_track)
        layout.addWidget(self.results_list)

 
        self.selected_track_label = QLabel("Selected: None")
        self.selected_track_label.setStyleSheet("font-size:16px; color:#1DB954;")
        layout.addWidget(self.selected_track_label)

 
        layout.addWidget(QLabel("Output filename:"))
        self.filename_input = QLineEdit("spotify_code.png")
        browse_btn = QPushButton("Browse Location")
        browse_btn.setFixedWidth(120)
        browse_btn.clicked.connect(self.browse_location)
        fl = QHBoxLayout(); fl.addWidget(self.filename_input); fl.addWidget(browse_btn)
        layout.addLayout(fl)

        layout.addWidget(QLabel("Code Preview:"))
        self.preview = QLabel(alignment=Qt.AlignCenter)
        self.preview.setFixedHeight(150)
        self.preview.setStyleSheet("background-color:#282828; border-radius:8px;")
        layout.addWidget(self.preview)

        self.generate_button = QPushButton("Generate Code")
        self.generate_button.clicked.connect(self.generate_code)
        self.generate_button.setEnabled(False)
        layout.addWidget(self.generate_button)

        self.status_bar = QLabel("Initializing…")
        self.status_bar.setStyleSheet("color:#B3B3B3; font-size:12px;")
        layout.addWidget(self.status_bar)

        self.selected_track = None

    def search_tracks(self):
        token_info = self.sp_oauth.get_cached_token()
        if not token_info:
            self.authenticate()
            return

        q = self.search_input.text().strip()
        if not q:
            return

        self.status_bar.setText("Searching…")
        self.results_list.clear()
        self.generate_button.setEnabled(False)

        self.worker = SearchWorker(q, self.sp_oauth)
        self.worker.search_complete.connect(self.display_results)
        self.worker.auth_needed.connect(self.authenticate)
        self.worker.start()

    def display_results(self, tracks):
        self.status_bar.setText(f"Found {len(tracks)} results")
        if not tracks:
            QMessageBox.information(self, "No Results", "No tracks found.")
            return
        for t in tracks:
            item = QListWidgetItem(f"{t['artist']} – {t['name']} ({t['album']})")
            item.setData(Qt.UserRole, t)
            if t['image']:
                data = requests.get(t['image']).content
                pix = QPixmap(); pix.loadFromData(data)
                item.setIcon(QIcon(pix.scaled(50,50,Qt.KeepAspectRatio,Qt.SmoothTransformation)))
            self.results_list.addItem(item)

    def select_track(self, item):
        t = item.data(Qt.UserRole)
        self.selected_track = t
        self.selected_track_label.setText(f"Selected: {t['artist']} – {t['name']}")
        safe = lambda s: "".join(c if c.isalnum() else "_" for c in s)
        self.filename_input.setText(f"{safe(t['artist'])}_{safe(t['name'])}.png")
        self.generate_button.setEnabled(True)

    def browse_location(self):
        fn = QFileDialog.getSaveFileName(self, "Save Spotify Code",
                                         self.filename_input.text(), "PNG Files (*.png)")[0]
        if fn:
            self.filename_input.setText(fn)

    def generate_code(self):
        if not self.selected_track:
            return
        out = self.filename_input.text().strip()
        if not out.lower().endswith('.png'):
            out += '.png'
        uri = self.selected_track['uri']
        url = f"https://scannables.scdn.co/uri/plain/png/000000/white/640/{uri}"
        try:
            self.status_bar.setText("Generating code…")
            QApplication.processEvents()
            resp = requests.get(url); resp.raise_for_status()
            img = Image.open(BytesIO(resp.content))
            img.save(out)
            img.thumbnail((400,150))
            img.save("preview.png")
            self.preview.setPixmap(QPixmap("preview.png"))
            self.status_bar.setText(f"Saved as: {os.path.basename(out)}")
            QMessageBox.information(self, "Success", "Spotify code generated!")
        except Exception as e:
            self.status_bar.setText("Error generating code")
            QMessageBox.critical(self, "Error", str(e))

if __name__ == "__main__":
    app = QApplication(sys.argv)
    font = app.font(); font.setFamily("Segoe UI"); app.setFont(font)
    window = SpotifyCodeGenerator()
    window.show()
    sys.exit(app.exec_())
