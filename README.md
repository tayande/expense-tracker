# Expense Tracker 

A beginner-friendly expense tracker with two ways to use it: a
command-line tool and a web app. Both save to the same expenses.json
file using plain functions and dictionaries — no classes involved.

## Setup
pip install flask

## Usage

### Command line
python3 cli_simple.py add 25.50 food "Lunch"
python3 cli_simple.py list
python3 cli_simple.py delete 1
python3 cli_simple.py summary

### Web app
python3 app_simple.py
# then open http://127.0.0.1:5000 in the browser

## Files
cli_simple.py              - command-line version
app_simple.py               - web version (needs Flask)
templates/index_simple.html - web page layout
static/style_simple.css     - web page styling
expenses.json                - where data is saved (created automatically)