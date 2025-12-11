# 📁 GitHub Repository Structure

## Recommended Folder Organization

```
command-gateway/
├── README.md                    # Main documentation with setup & demo
├── requirements.txt             # Python dependencies
├── .gitignore                   # Git ignore file
│
├── backend/                     # Backend Code
│   ├── app.py                   # Main Flask application
│   ├── models.py                # Database models and AI logic
│   ├── config.py                # Configuration settings
│   └── init_db.py               # Database initialization
│
├── frontend/                    # Frontend Code
│   ├── templates/
│   │   └── index.html           # Main web interface
│   └── static/
│       ├── app.js               # Frontend JavaScript
│       └── style.css            # Styling
│
├── tests/                       # Test Suite
│   ├── test_app.py              # Unit tests
│   ├── test_integration.py      # Integration tests
│   ├── test_isolated.py         # Isolated tests
│   ├── test_regex_validation.py # Regex validation tests
│   └── test_conflict_detection.py # Conflict detection tests
│
├── demos/                       # Demo Scripts
│   ├── demo.py                  # Main demo script
│   ├── ai_demo.py               # AI features demo
│   ├── regex_demo.py            # Regex validation demo
│   └── test_conflict_frontend.html # Frontend test page
│
├── docs/                        # Documentation
│   ├── AI_FEATURES.md           # AI integration details
│   ├── BONUS_FEATURES.md        # Bonus features overview
│   ├── CONFLICT_DETECTION.md    # Conflict detection system
│   ├── REGEX_VALIDATION.md      # Regex validation system
│   └── SUMMARY.md               # Project summary
│
└── demo-video/                  # Demo Video
    ├── demo-video.mp4           # 2-3 minute demo video
    └── demo-script.md           # Video script/walkthrough
```

## Files to Move

### Backend Code → `backend/`
- app.py
- models.py  
- config.py
- init_db.py

### Frontend Code → `frontend/`
- templates/index.html → frontend/templates/
- static/app.js → frontend/static/
- static/style.css → frontend/static/

### Tests → `tests/`
- test_app.py
- test_integration.py
- test_isolated.py
- test_regex_validation.py
- test_conflict_detection.py

### Demos → `demos/`
- demo.py
- ai_demo.py
- regex_demo.py
- test_conflict_frontend.html

### Documentation → `docs/`
- AI_FEATURES.md
- BONUS_FEATURES.md
- CONFLICT_DETECTION.md
- REGEX_VALIDATION.md
- SUMMARY.md

## Commands to Reorganize

```bash
# Create directories
mkdir backend frontend tests demos docs demo-video

# Move backend files
mv app.py models.py config.py init_db.py backend/

# Move frontend files
mkdir -p frontend/templates frontend/static
mv templates/index.html frontend/templates/
mv static/app.js static/style.css frontend/static/

# Move test files
mv test_*.py tests/

# Move demo files
mv demo.py ai_demo.py regex_demo.py test_conflict_frontend.html demos/

# Move documentation
mv *_FEATURES.md *_DETECTION.md *_VALIDATION.md SUMMARY.md docs/

# Update import paths in files after moving
```

## .gitignore File

```gitignore
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
*.egg-info/
.installed.cfg
*.egg

# Database
*.db
*.sqlite
*.sqlite3

# Environment
.env
.venv
env/
venv/
ENV/
env.bak/
venv.bak/

# IDE
.vscode/
.idea/
*.swp
*.swo
*~

# OS
.DS_Store
.DS_Store?
._*
.Spotlight-V100
.Trashes
ehthumbs.db
Thumbs.db

# Logs
*.log
logs/

# Demo video (if large)
# demo-video/*.mp4
```