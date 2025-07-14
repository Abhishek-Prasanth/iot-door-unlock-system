# populate_users.py
import os
import uuid
from recognition_server import app, db, User, pwd_context, KNOWN_FACES_PATH 

DEFAULT_TEMP_PASSWORD = "changeme123" 

def run():
    print("Scanning known_faces directory...")
    if not os.path.isdir(KNOWN_FACES_PATH):
        print(f"ERROR: Directory not found: {KNOWN_FACES_PATH}")
        return

    with app.app_context(): # Need app context for DB operations
        found_folders = [d for d in os.listdir(KNOWN_FACES_PATH)
                         if os.path.isdir(os.path.join(KNOWN_FACES_PATH, d))]

        if not found_folders:
            print("No user subdirectories found in known_faces.")
            return

        print(f"Found potential user folders: {', '.join(found_folders)}")
        added_count = 0

        for folder_name in found_folders:
            # Assume folder name is the user ID (ideally a UUID)
            user_id = folder_name
            existing_user = User.query.get(user_id)

            if existing_user:
                print(f"Skipping '{folder_name}': User already exists in database.")
                continue

            # --- Create new user record ---
            print(f"Creating database entry for user ID: {user_id}...")

            # Basic validation (is it a UUID? optional)
            try:
                 uuid.UUID(user_id, version=4)
            except ValueError:
                 print(f"  WARN: Folder name '{user_id}' is not a valid UUID. Skipping for safety.")
                 # Or you could generate a new UUID and rename folder? Risky.
                 continue


            # Generate placeholder details
            email = f"{user_id}@neuralock.placeholder"
            name = user_id # Use ID as name initially, user can change via app
            role = "Family Member" # Default role
            password_hash = pwd_context.hash(DEFAULT_TEMP_PASSWORD)

            # Check if placeholder email already exists (shouldn't if ID is unique)
            if User.query.filter_by(email=email).first():
                 print(f"  WARN: Placeholder email '{email}' already exists. Skipping user '{user_id}'.")
                 continue

            try:
                new_user = User(
                    id=user_id,
                    email=email,
                    name=name, # User should update this via profile screen
                    password_hash=password_hash,
                    role=role
                    # Avatar will remain default for now
                )
                db.session.add(new_user)
                print(f"  Added user '{name}' (ID: {user_id}) with placeholder details.")
                added_count += 1

            except Exception as e:
                print(f"  ERROR adding user '{user_id}' to database session: {e}")
                db.session.rollback() # Rollback this specific user on error

        # Commit all successfully added users outside the loop
        if added_count > 0:
            try:
                db.session.commit()
                print(f"\nSuccessfully added {added_count} users to the database.")
                print(f"IMPORTANT: Default password is '{DEFAULT_TEMP_PASSWORD}'. Users must log in and change details.")
                # Force DeepFace re-index as DB state changed relative to known faces
                trigger_deepface_reindex()
            except Exception as e:
                print(f"\nERROR committing users to database: {e}")
                db.session.rollback()
        else:
            print("\nNo new users were added to the database.")


if __name__ == "__main__":
    run()