# Expense Tracker

A simple Python expense tracker with two interfaces — a command-line tool
and a Flask web app — sharing the same core logic and JSON data file.

## Features
- Add, list, filter, and delete expenses
- Category-based spending summary
- CLI and web UI, both backed by the same tracker logic

## Setup
pip install flask

## Usage
# Web app
python3 app.py            # then visit http://127.0.0.1:5000

# CLI
python3 cli.py add --amount 25.50 --category food --note "Lunch"
python3 cli.py list
python3 cli.py summary

## Structure
tracker.py       - core Expense/ExpenseTracker logic
cli.py            - command-line interface
app.py            - Flask web interface
templates/        - HTML templates
static/           - CSS
expenses.json     - data file (auto-created)