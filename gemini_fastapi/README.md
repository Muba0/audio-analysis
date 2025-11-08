# Audio Analysis Service with Gemini AI

A production-ready audio transcription and analysis web application using FastAPI, Celery, and Google Gemini AI.

## 🚀 Features

- **Audio Transcription**: Upload MP3/WAV/OGG files for AI-powered analysis
- **Comprehensive Reports**: Detailed transcription with timestamps, context, and insights
- **Asynchronous Processing**: Celery-based task queue for scalable processing
- **Auto-scaling**: Dynamic worker management based on load
- **Modern UI**: Responsive web interface with real-time progress updates
- **API Key Management**: Intelligent rotation for rate limiting

## 🛠️ Tech Stack

- **Backend**: FastAPI, Python 3.11
- **AI**: Google Gemini 2.0 Flash
- **Queue**: Celery + Redis
- **Frontend**: HTML5, Bootstrap, Tailwind CSS
- **Deployment**: Docker + Docker Compose

## 📋 Prerequisites

- Docker & Docker Compose
- Google Gemini API key
- Git

## 🚀 Quick Start (Local Development)

1. **Clone the repository**
   ```bash
   git clone <your-repo-url>
   cd audio-analysis-gemini
   ```

2. **Set up environment variables**
   ```bash
   cp .env.example .env
   # Edit .env and add your GOOGLE_API_KEY_0
   ```

3. **Run with Docker Compose**
   ```bash
   docker compose up --build
   ```

4. **Access the application**
   - Web Interface: http://localhost:8001
   - Health Check: http://localhost:8001/health

## 🌐 Deployment Options

### Option 1: Railway (Recommended - Free Tier)

1. **Create Railway Account**
   - Go to https://railway.app
   - Sign up with GitHub

2. **Connect Repository**
   - Click "New Project" → "Deploy from GitHub repo"
   - Select your repository

3. **Configure Services**
   - Railway auto-detects `docker-compose.yml`
   - Add environment variables in Railway dashboard:
     ```
     GOOGLE_API_KEY_0=your_actual_api_key
     ```

4. **Deploy**
   - Railway automatically builds and deploys
   - Get your deployment URL

### Option 2: Render

1. **Create Render Account**
   - https://render.com

2. **Create Web Service**
   - Connect GitHub repo
   - Select Docker
   - Set build command: `docker build -t myapp .`
   - Set start command: `docker run myapp`

3. **Add Environment Variables**
   - Set `GOOGLE_API_KEY_0`

### Option 3: Fly.io

1. **Install Fly CLI**
   ```bash
   curl -L https://fly.io/install.sh | sh
   ```

2. **Deploy**
   ```bash
   fly launch
   fly deploy
   ```

## 🔧 Configuration

### Environment Variables

```bash
# Required
GOOGLE_API_KEY_0=your_google_gemini_api_key

# Optional (with defaults)
REDIS_URL=redis://redis:6379/0
MIN_WORKERS=3
MAX_WORKERS=20
```

### Multiple API Keys

For higher rate limits, add multiple keys:
```bash
GOOGLE_API_KEY_0=key1
GOOGLE_API_KEY_1=key2
GOOGLE_API_KEY_2=key3
```

## 📁 Project Structure

```
├── .env.example           # Environment variables template
├── .github/workflows/     # GitHub Actions CI/CD
├── .gitignore             # Git ignore rules
├── README.md              # Project documentation
├── app.py                 # FastAPI application
├── apimanager.py          # API key management
├── docker-compose.yml     # Local development setup
├── Dockerfile             # Container build configuration
├── healthcheck.py         # Health check script
├── prompt_1.txt           # AI analysis prompt
├── requirements.txt       # Python dependencies
├── scaler.py              # Auto-scaling service
├── tasks.py               # Celery tasks
├── transcription.py       # AI processing logic
├── nginx/                 # Nginx configuration
├── static/                # Static files
├── templates/             # HTML templates
└── uploads/               # File uploads (gitignored)
```

## 🔍 API Endpoints

- `GET /` - Web interface
- `POST /process_audio` - Upload and process audio
- `GET /task_status/{task_id}` - Check processing status
- `GET /results/{task_id}` - Get results
- `GET /health` - Health check

## 🧪 Testing

```bash
# Run health check
python healthcheck.py

# Manual testing
curl http://localhost:8001/health

# Run tests (when implemented)
python -m pytest
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## 📄 License

MIT License - see LICENSE file for details

## ⚠️ Important Notes

- **API Keys**: Never commit real API keys to version control
- **File Storage**: Uploaded files are automatically cleaned up after processing
- **Rate Limits**: The app includes intelligent API key rotation to handle rate limits
- **Scaling**: Workers automatically scale based on queue length

## 🆘 Troubleshooting

**Common Issues:**

1. **Port conflicts**: Change ports in `docker-compose.yml`
2. **API key errors**: Verify your Google Gemini API key
3. **Memory issues**: Reduce worker concurrency in production
4. **Build failures**: Ensure Docker is properly installed

**Logs:**
```bash
# View application logs
docker compose logs -f web

# View worker logs
docker compose logs -f worker
