from flask import Flask, request, jsonify, render_template, redirect, url_for, session
import os
import requests
import json

# Configure Flask to search the current folder for templates
app = Flask(__name__, template_folder='.')
app.secret_key = os.urandom(24)  # Required for session management

# Load API key from environment variables
api_key = os.getenv("SAMBANOVA_API_KEY")
if not api_key:
    raise ValueError("API key not found. Ensure it is set in the environment variables.")

@app.route('/')
def index():
    return render_template('index.html')  # Load index.html from the same folder

@app.route('/generate-plan', methods=['POST'])
def generate_plan():
    data = request.get_json()
    goal = data.get('goal')
    days = data.get('days')

    # Create a day-specific prompt for the SambaNova API
    prompt = (
    f"Generate a detailed day-wise plan to achieve the goal '{goal}' in {days} days. "
    f"For each day, provide a specific task that helps in achieving the goal, along with 10 practice questions or exercises "
    f"that focus on the day's task. Ensure the questions are varied and challenging"
    f"Format the response as 'Day 1: Task for Day 1. Practice Questions: 1. Question 1, 2. Question 2, ..., 10. Question 10\\n"
    f"Day 2: Task for Day 2. Practice Questions: 1. Question 1, 2. Question 2, ..., 10. Question 10' and continue in this manner for each day."
)



    # Define the API endpoint and model
    base_url = "https://api.sambanova.ai/v1/chat/completions"
    model = "Meta-Llama-3.1-8B-Instruct"

    # Prepare the payload
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.1,
        "top_p": 0.1,
        "stream": True
    }

    # Set the request headers
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    response_text = ""
    try:
        # Make a request to the SambaNova API
        response = requests.post(base_url, json=payload, headers=headers, stream=True)
        response.raise_for_status()  # Check for HTTP errors

        # Stream and accumulate content from the response
        for chunk in response.iter_lines():
            if chunk:
                chunk_decoded = chunk.decode('utf-8').lstrip('data: ')
                if chunk_decoded == "[DONE]":
                    break

                try:
                    data = json.loads(chunk_decoded)
                    content = data['choices'][0]['delta'].get('content', '')
                    response_text += content
                except json.JSONDecodeError:
                    print("Could not decode JSON from chunk:", chunk_decoded)

        # Split the response into a structured plan based on day-task pairs
        tasks = response_text.strip().split('\n')
        plan = []
        current_day = None
        current_task = []

        # Iterate through the split tasks to correctly gather each day's plan
        for task in tasks:
            if "Day " in task:  # Check for the start of a new day
                if current_day:
                    # Save the previous day's task
                    plan.append({'day': current_day, 'task': ' '.join(current_task).strip()})
                
                # Extract the day and start a new task collection
                parts = task.split(':', 1)
                current_day = parts[0].strip()
                current_task = [parts[1].strip()] if len(parts) > 1 else []
            else:
                # Continue adding lines to the current day's task
                current_task.append(task.strip())

        # Add the final day's task if there is any remaining
        if current_day:
            plan.append({'day': current_day, 'task': ' '.join(current_task).strip()})

        # Store the generated plan in session
        session['plan'] = plan  # Store as a list of dictionaries

        # Check if the plan is empty
        if not plan:
            return jsonify({'error': 'No tasks generated.'}), 400

        return jsonify({'redirect': url_for('cards')})  # Send back the redirect URL

    except Exception as e:
        print(f"Error: {e}")
        return jsonify({'error': 'Failed to generate plan.'}), 500


@app.route('/cards')
def cards():
    plan = session.get('plan', [])
    print("Plan passed to cards:", plan)  # Debugging output
    return render_template('card.html', plan=plan)  # Pass the plan to card.html

if __name__ == '__main__':
    app.run(debug=True)
