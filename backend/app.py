from backend import app, db
from backend.routes.auth_routes import auth_blueprint
from backend.routes.stock_routes import stock_blueprint
from flask import render_template
import os

# Register blueprints
app.register_blueprint(auth_blueprint, url_prefix="/auth")
app.register_blueprint(stock_blueprint)  # , url_prefix="/stocks")

app.config['SQLALCHEMY_ECHO'] = True

print("Debug Mode:", app.debug)
print("Testing Mode:", app.testing)


if not os.getenv('FLASK_ENV'):
    os.environ['FLASK_ENV'] = 'development'


# Add a root route
@app.route("/")
def home():
    return render_template("home.html")


# Run the application
if __name__ == "__main__":
    # with app.app_context():
    #     db.create_all()  # Ensure database tables are created
    app.run(debug=True)
