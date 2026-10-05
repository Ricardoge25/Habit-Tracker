# Habit Tracker — Backend

Django REST API for a full-stack habit tracking application.

The backend provides the API consumed by the React frontend and manages habit data, user-related functionality, and application logic.

## Overview

Habit Tracker is a full-stack web application built to practice and demonstrate backend and frontend development with Django REST Framework and React.

The backend is implemented with Django and Django REST Framework and is deployed on Render. The application uses PostgreSQL hosted on Supabase for persistent data storage.

## Features

- REST API built with Django REST Framework
- Habit creation and management
- Daily habit tracking
- Habit history
- Streak tracking
- User-specific habit data
- Authentication and protected API resources
- PostgreSQL database integration
- Docker support
- Production deployment on Render

## Tech Stack

- **Language:** Python
- **Backend:** Django, Django REST Framework
- **Database:** PostgreSQL
- **Database Hosting:** Supabase
- **Containerization:** Docker
- **Deployment:** Render
- **Version Control:** Git, GitHub

## Project Structure

```text
Habit-Tracker/
├── habit_tracker/
├── habits/
├── .dockerignore
├── .gitignore
├── Dockerfile
├── Dockerfile.prod
├── manage.py
└── requirements.txt
```

### Main Applications

- **habit_tracker:** Main Django project configuration.
- **habits:** Application responsible for habit-related functionality and tracking.

## Architecture

The backend is part of a separated frontend/backend architecture:

```text
React + Vite Frontend
        │
        │ REST API
        ▼
Django REST Framework
        │
        ▼
PostgreSQL
        │
        ▼
     Supabase
```

## Deployment

The backend is deployed on **Render**.

The project uses GitHub as the source repository and supports continuous deployment from the repository.

The PostgreSQL database is hosted on **Supabase**.

## Running Locally

### Prerequisites

- Python 3.x
- pip
- Git
- PostgreSQL or access to a PostgreSQL database

### Installation

Clone the repository:

```bash
git clone https://github.com/Ricardoge25/Habit-Tracker.git
cd Habit-Tracker
```

Create a virtual environment:

```bash
python -m venv venv
```

Activate it on Windows:

```bash
venv\Scripts\activate
```

On macOS/Linux:

```bash
source venv/bin/activate
```

Install the dependencies:

```bash
pip install -r requirements.txt
```

Apply migrations:

```bash
python manage.py migrate
```

Run the development server:

```bash
python manage.py runserver
```

## Docker

The repository includes Docker configuration for containerized development and production environments.

Available configuration includes:

- `Dockerfile`
- `Dockerfile.prod`

## Project Status

The backend is actively deployed as part of the Habit Tracker application.

## Author

**Ricardo González**

Software Engineer | Backend & Full Stack Developer

GitHub: https://github.com/Ricardoge25
