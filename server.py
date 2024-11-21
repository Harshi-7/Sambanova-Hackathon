from flask import Flask, request, jsonify, render_template, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
import os
import requests
import json
import random
import bcrypt

# Configure Flask to search the current folder for templates
app = Flask(__name__, template_folder='.')
app.secret_key = os.urandom(24)  # Required for session management

# Load API key from environment variables
api_key = os.getenv("SAMBANOVA_API_KEY")
if not api_key:
    raise ValueError("API key not found. Ensure it is set in the environment variables.")

# Configure SQLite database
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize SQLAlchemy only once
db = SQLAlchemy(app)

# User model for registration and login
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)

    def __init__(self, name, email, password):
        self.name = name
        self.email = email
        self.password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    def check_password(self, password):
        return bcrypt.checkpw(password.encode('utf-8'), self.password.encode('utf-8'))

# Schedule model to store generated schedules
class Schedule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    day = db.Column(db.String(20), nullable=False)
    task = db.Column(db.Text, nullable=False)

# Initialize database only once
with app.app_context():
    db.create_all()

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        new_user = User(name=name, email=email, password=password)
        db.session.add(new_user)
        db.session.commit()
        return redirect('/login')
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            session['name'] = user.name
            session['email'] = user.email
            return redirect(url_for('features'))
        else:
            return render_template('login.html', error='Invalid email or password.')
    return render_template('login.html')

@app.route('/features')
def features():
    return render_template('features.html')  # Load features.html from the same folder

@app.route('/generate-plan', methods=['POST'])
def generate_plan():
    data = request.get_json()
    goal = data.get('goal')
    days = data.get('days')

    # Create a day-specific prompt for the SambaNova API
    prompt = (
        f"Generate a detailed day-wise plan to achieve the goal '{goal}' in {days} days. "
        f"For each day, provide a specific task that helps in achieving the goal, along with 10 practice questions or exercises "
        f"that focus on the day's task. Ensure the questions are varied and challenging. "
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


@app.route('/facts')
def facts():
    # Clear previous facts on new request
    session.pop('facts', None)

    # Create a unique prompt without showing the unique ID
    prompt = (
        "Generate 50 unique and interesting facts on a variety of topics. Each fact should be different from the others. "
        "Format the response as a list with bullet points, without numbering or any unique identifiers. "
        "Each fact should be presented with a bullet point."
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
        "temperature": 0.8,  # Increase temperature for more randomness
        "top_p": 1.0,  # Use full probability mass
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

        # Clean up the response and split it into a list of facts
        # Replacing any inconsistent bullet points with a single standard one
        response_text = response_text.replace('•', '').replace('-', '•').replace('*', '•')

        # Remove unwanted spaces or blank lines
        facts_list = [
            fact.strip() for fact in response_text.split('\n') if fact.strip()
        ]
        session['facts'] = facts_list  # Store facts in session

        return render_template('facts.html', facts=facts_list)  # Render facts.html with the facts

    except Exception as e:
        print(f"Error: {e}")
        return jsonify({'error': 'Failed to generate facts.'}), 500


@app.route('/quotes')
def quotes():
    # Clear previous quotes on new request
    session.pop('quotes', None)

    # Create a unique prompt with a random element
    unique_id = random.randint(1, 10000)  # Generates a random number
    prompt = (
        f"Generate 10 unique and inspirational quotes about life, success, and motivation. "
        f"Each quote should be distinct and thought-provoking. "
        f"Include a unique ID ({unique_id}) for this request to ensure the quotes are varied. "
        "Format the response as a list, with each quote on a new line."
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
        "temperature": 0.8,  # Increase temperature for more randomness
        "top_p": 1.0,  # Use full probability mass
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

        # Split the response into a list of quotes
        quotes_list = response_text.strip().split('\n')
        session['quotes'] = quotes_list  # Store quotes in session

        return render_template('quotes.html', quotes=quotes_list)  # Render quotes.html with the quotes

    except Exception as e:
        print(f"Error: {e}")
        return jsonify({'error': 'Failed to generate quotes.'}), 500
    





# @app.route('/quiz', methods=['GET', 'POST'])
# def quiz():
#     session.pop('quiz', None)  # Clear previous quiz

#     if request.method == 'POST':
#         topic = request.form.get('topic')  # Get the topic from the form
#         if not topic:
#             return jsonify({'error': 'Topic is required'}), 400
#     else:
#         return render_template('quiz_form.html')  # Show form if GET request

#     print(f"Generating quiz for topic: {topic}")  # Debugging

#     # API prompt for generating quiz
#     prompt = (
#         f"Create a quiz on {topic} with 5 questions. Each question should include: "
#         "1 question and 4 multiple-choice options, with the correct answer marked as the first option. "
#         "Format: Question: followed by options on the next lines."
#     )

#     base_url = "https://api.sambanova.ai/v1/chat/completions"
#     model = "Meta-Llama-3.1-8B-Instruct"
#     payload = {
#         "model": model,
#         "messages": [
#             {"role": "system", "content": "You are a helpful assistant."},
#             {"role": "user", "content": prompt}
#         ],
#         "temperature": 0.7,
#         "top_p": 1.0,
#         "stream": False
#     }
#     headers = {
#         "Authorization": f"Bearer {api_key}",
#         "Content-Type": "application/json"
#     }

#     try:
#         response = requests.post(base_url, json=payload, headers=headers)
#         response.raise_for_status()
#         data = response.json()
        
#         if "choices" in data and data["choices"]:
#             response_text = data["choices"][0].get("message", {}).get("content", "")
#             print("Generated Quiz Response:", response_text)  # Debugging

#             # Parse the quiz text into structured data
#             quiz_list = []
#             raw_questions = response_text.strip().split('\n\n')  # Assuming each question block is separated by a blank line
            
#             for raw_question in raw_questions:
#                 lines = raw_question.strip().split('\n')
#                 if len(lines) >= 2:
#                     question = lines[0].strip()
#                     options = [line.strip() for line in lines[1:]]
#                     if len(options) == 4:  # Ensure there are exactly 4 options
#                         quiz_list.append({"question": question, "options": options})

#             if quiz_list:
#                 session['quiz'] = quiz_list  # Store the quiz in session
#                 return render_template('quiz.html', quiz=quiz_list, topic=topic)
#             else:
#                 return jsonify({'error': 'Failed to parse quiz data.'}), 500

#         else:
#             print("API did not return valid choices.")
#             return jsonify({'error': 'API response is invalid.'}), 500

#     except Exception as e:
#         print(f"Error occurred: {e}")
#         return jsonify({'error': 'Failed to generate quiz due to an error.'}), 500



    


@app.route('/chatbot', methods=['GET', 'POST'])
def chatbot():
    if request.method == 'POST':
        # Get the user message from the request (this will be JSON in the body)
        user_message = request.json.get('message', '').strip()

        # Validate that the user message is not empty
        if not user_message:
            return jsonify({'error': 'Message cannot be empty.'}), 400

        # Define the API endpoint and model
        base_url = "https://api.sambanova.ai/v1/chat/completions"
        model = "Meta-Llama-3.1-8B-Instruct"

        # Prepare the payload for the API request
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": user_message}
            ],
            "temperature": 0.7,  # Adjust randomness
            "top_p": 1.0,
            "stream": True
        }

        # Set the request headers
        headers = {
            "Authorization": f"Bearer {api_key}",  # Replace with your actual API key
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

            return jsonify({'response': response_text.strip()})

        except Exception as e:
            print(f"Error: {e}")
            return jsonify({'error': 'Failed to generate chatbot response.'}), 500

    return render_template('chatbot.html')  # Render the chatbot UI



@app.route('/quiz', methods=['GET', 'POST'])
def quiz():
    if request.method == 'POST':
        # Check if the user is submitting answers
        if 'quiz' in session:
            quiz_list = session['quiz']
            results = []
            for idx, q in enumerate(quiz_list):
                user_answer = request.form.get(f'q{idx}')
                correct_answer = q['correct_answer']
                is_correct = user_answer == correct_answer
                results.append({
                    "question": q["question"],
                    "user_answer": user_answer,
                    "correct_answer": correct_answer,
                    "is_correct": is_correct
                })
            return render_template('quiz.html', quiz=quiz_list, topic=session.get('topic'), results=results)

    # Generate quiz on GET request
    session.pop('quiz', None)  # Clear previous quiz
    if request.method == 'POST':
        topic = request.form.get('topic', '').strip()
        if not topic:
            return render_template('quiz_form.html', error="Topic is required.")  # Show error if topic is missing

        prompt = (
            f"Create a quiz on the topic '{topic}' with 5 questions. Each question should include:\n"
            "1 question and 4 multiple-choice options, with the correct answer marked as the first option.\n"
            "Format: Question: [question text] followed by options on separate lines, e.g.,\n"
            "1. Option 1\n2. Option 2\n3. Option 3\n4. Option 4."
        )

        base_url = "https://api.sambanova.ai/v1/chat/completions"
        model = "Meta-Llama-3.1-8B-Instruct"
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.7,
            "top_p": 1.0,
            "stream": False
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        try:
            response = requests.post(base_url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

            if "choices" in data and data["choices"]:
                response_text = data["choices"][0].get("message", {}).get("content", "")
                print("Generated Quiz Response:", response_text)  # Debugging

                quiz_list = []
                raw_questions = response_text.strip().split('\n\n')  # Each question block is separated by blank lines

                for raw_question in raw_questions:
                    lines = raw_question.strip().split('\n')
                    if len(lines) >= 5:  # Ensure each block contains a question + 4 options
                        question = lines[0].replace('Question:', '').strip()
                        options = [line.strip() for line in lines[1:5]]  # Extract exactly 4 options
                        correct_answer = options[0]  # First option is the correct answer
                        quiz_list.append({"question": question, "options": options, "correct_answer": correct_answer})

                if quiz_list:
                    session['quiz'] = quiz_list  # Store the quiz in session
                    session['topic'] = topic
                    return render_template('quiz.html', quiz=quiz_list, topic=topic)
                else:
                    return render_template('quiz_form.html', error="Failed to parse quiz data.")

            else:
                return render_template('quiz_form.html', error="API response is invalid.")

        except Exception as e:
            print(f"Error occurred: {e}")
            return render_template('quiz_form.html', error="Failed to generate quiz due to an error.")

    return render_template('quiz_form.html')

@app.route('/timer')
def timer():
    return render_template('timer.html')  # Load timer.html from the same folder

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/card')
def cards():
    plan = session.get('plan', [])
    print("Plan passed to cards:", plan)  # Debugging output
    return render_template('card.html', plan=plan)  # Pass the plan to card.html

@app.route('/save-schedule', methods=['POST'])
def save_schedule():
    data = request.get_json()
    name = data.get('name')
    tasks = data.get('tasks')
    if not name or not tasks:
        return jsonify({'error': 'Invalid schedule data.'}), 400
    for task in tasks:
        new_schedule = Schedule(name=name, day=task['day'], task=task['task'])
        db.session.add(new_schedule)
    db.session.commit()
    return jsonify({'message': 'Schedule saved successfully.'}), 200

@app.route('/vs')
def vs():
    schedules = Schedule.query.all()
    schedule_dict = {}
    for schedule in schedules:
        if schedule.name not in schedule_dict:
            schedule_dict[schedule.name] = []
        schedule_dict[schedule.name].append({'day': schedule.day, 'task': schedule.task})
    return render_template('vs.html', schedules=schedule_dict)



@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')

@app.route('/index')
def indexs():
    return render_template('index.html')

@app.route('/')
def index():
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)
