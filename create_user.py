import sys
import os
from dotenv import load_dotenv
from getpass import getpass  # For securely getting password input

# Add project root to sys.path to allow importing models etc.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__))))

load_dotenv()

from models import SessionLocal, User
from app import set_password  # Import password hashing function from app.py
from sqlalchemy.exc import IntegrityError

def create_first_user():
    """ Creates the initial user account """
    print("--- Create Initial User ---")

    while True:
        username = input("Enter username: ").strip()
        if username:
            break
        else:
            print("Username cannot be empty.")

    while True:
        password = getpass("Enter password: ")
        password2 = getpass("Confirm password: ")
        if password == password2:
            if password: # Ensure password is not empty
                break
            else:
                print("Password cannot be empty.")
        else:
            print("Passwords do not match. Please try again.")

    # Hash the password
    password_hash = set_password(password)

    db = SessionLocal()
    try:
        # Check if user already exists
        existing_user = db.query(User).filter_by(username=username).first()
        if existing_user:
            print(f"Error: Username '{username}' already exists.")
            return

        # Create new user
        new_user = User(username=username, password_hash=password_hash)
        db.add(new_user)
        db.commit()
        print(f"Successfully created user '{username}'.")

    except IntegrityError:
        db.rollback()
        print(f"Error: Username '{username}' already exists (IntegrityError).")
    except Exception as e:
        db.rollback()
        print(f"An unexpected error occurred: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    create_first_user()