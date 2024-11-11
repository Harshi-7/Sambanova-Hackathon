# from flask import Flask, request, jsonify, render_template
# from flask_sqlalchemy import SQLAlchemy

# app = Flask(__name__)
# app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///goals.db'  # SQLite database file
# app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
# db = SQLAlchemy(app)

# # Define your Goal model
# class Goal(db.Model):
#     id = db.Column(db.Integer, primary_key=True)
#     goal = db.Column(db.String(200), nullable=False)
#     days = db.Column(db.Integer, nullable=False)

#     def __repr__(self):
#         return f'<Goal {self.goal}>'

# # Home route to serve the HTML page
# @app.route('/')
# def home():
#     return render_template('index.html')  # Use render_template if index.html is in 'templates'

# # Endpoint to handle goal submission
# @app.route('/generate-plan', methods=['POST'])
# def generate_plan():
#     data = request.json
#     print("Received data:", data)  # Log the incoming data for debugging

#     # Validate incoming data
#     if not data or 'goal' not in data or 'days' not in data:
#         return jsonify({'message': 'Invalid data!'}), 400  # Bad Request

#     goal_text = data.get('goal')
#     days = data.get('days')

#     # Create a new Goal instance
#     new_goal = Goal(goal=goal_text, days=days)

#     # Add to the database
#     db.session.add(new_goal)
#     db.session.commit()

#     return jsonify({'message': 'Goal stored successfully!', 'redirect': '/cards.html'}), 200

# if __name__ == '__main__':
#     with app.app_context():  # Set the application context
#         db.create_all()  # Create database tables if they don't exist
#     app.run(debug=True)  # Run the application in debug mode
