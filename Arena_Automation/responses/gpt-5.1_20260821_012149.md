# Model Evaluation: gpt-5.1

**Date:** 2026-08-21 01:21:49

## Prompt

```
Write a Python script that connects to Chrome over CDP on port 19333 and lists all open tabs.
```

## Response

I will create an index.html single-page site that displays the requested Python script (to connect to Chrome’s CDP on port 19333 and list all open tabs), along with brief usage instructions. The page will use Tailwind via CDN and a small JavaScript snippet to support a “Copy to clipboard” button for the script.

Created index.html

I’ve created a single-page site (index.html) that contains:

A ready-to-use Python script that:
Connects to Chrome’s DevTools HTTP endpoint at http://127.0.0.1:19333/json
Lists all open CDP targets (tabs, etc.), printing title, URL, and ID
Handles connection and HTTP errors cleanly
Step‑by‑step usage instructions:
pip install requests
Start Chrome with --remote-debugging-port=19333
Save and run the script (e.g., python list_tabs.py)
A “Copy” button (implemented in JavaScript) so you can copy the script from the page in one click
Tailwind CSS via the specified CDN for styling

Open index.html in your browser, copy the script from the page, save it as a .py file, and run it to list all open Chrome tabs via CDP on port 19333.

Deployed the project
Show More




01a020ba-130a-7424-93f2-f998...arena.site
