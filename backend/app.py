from backend import app, db
from backend.routes.auth_routes import auth_blueprint
from flask import render_template

# Register blueprints
app.register_blueprint(auth_blueprint, url_prefix="/auth")
app.config['SQLALCHEMY_ECHO'] = True


# Add a root route
@app.route("/")
def home():
    return render_template("home.html")


# Run the application
if __name__ == "__main__":
    # with app.app_context():
    #     db.create_all()  # Ensure database tables are created
    app.run(debug=True)
