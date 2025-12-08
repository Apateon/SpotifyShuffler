import os
from dotenv import load_dotenv
from SpotiShuffler import app, db, get_background_sp_client, update_history

load_dotenv()

def run_update():
    print("Starting scheduled update")
    with app.app_context():
        from SpotiShuffler import ShufflerUser
        user = db.session.execute(db.select(ShufflerUser)).scalars().first()

        if user:
            sp_client = get_background_sp_client()
            if sp_client:
                update_history(user.id, sp_client)
            else:
                print("Failed to authenticate")
        else:
            print("No users found in the database")

if __name__ == '__main__':
    run_update()