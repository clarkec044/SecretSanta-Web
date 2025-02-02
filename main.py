from flask import Flask, render_template, redirect, jsonify
import redis
import random
import logging
import os
import datetime

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Load configuration
config = {
    "port": int(os.getenv("APP_PORT", 5000)),
    "reroll_enabled": os.getenv("REROLL_ENABLED", "true").lower() == "true",
    "admin_user": os.getenv("ADMIN_USER", "admin"),
    "names": os.getenv("VALID_NAMES", "").split(","),
    "year": os.getenv("YEAR", datetime.datetime.now().year),
    "budget": os.getenv("BUDGET", "10")
}

app = Flask(__name__)

# Connect to Redis
def connect_redis():
    try:
        return redis.StrictRedis(
            host=os.getenv("REDIS_HOST", "redis"),
            port=int(os.getenv("REDIS_PORT", 6379)),
            db=0,
            decode_responses=True
        )
    except redis.ConnectionError as e:
        logging.error(f"Redis connection failed: {e}")
        raise

redis_client = connect_redis()

@app.route("/")
def main():
    return render_template("index.html")

@app.route("/rules/<firstname>/<recipient>")
def rules(firstname, recipient):
    return render_template(
        "rules.html",
        chosen_recipient_capital=recipient.capitalize(),
        config=config,
        firstname=firstname,
        reroll_enabled=config["reroll_enabled"]
    )

@app.route("/name/<firstname>")
def name(firstname: str):
    firstname_lower = firstname.lower()
    if firstname_lower not in config["names"]:
        return render_template(
            "error.html",
            message=(
                "Oh no! Make sure you have spelled your name correctly. "
                f"Contact {config['admin_user']} if you believe there is a mistake."
            ),
        )

    try:
        # Check if the user has already been assigned a recipient
        recipient = redis_client.get(f"recipient:{firstname_lower}")
        if recipient:
            return render_template(
                "error.html",
                message=f"You have already been assigned a recipient. Contact {config['admin_user']} for assistance."
            )

        # Get available recipients
        all_names = set(config["names"])
        assigned_recipients = set(redis_client.smembers("assigned_recipients"))
        available_recipients = list(all_names - assigned_recipients - {firstname_lower})

        if not available_recipients:
            return render_template(
                "error.html",
                message="No available recipients left. Contact admin for assistance."
            )

        chosen_recipient = random.choice(available_recipients)

        # Assign the recipient
        redis_client.set(f"recipient:{firstname_lower}", chosen_recipient)
        redis_client.sadd("assigned_recipients", chosen_recipient)

        return redirect(f"/rules/{firstname_lower}/{chosen_recipient}")

    except redis.RedisError as e:
        logging.error(f"Redis error: {e}")
        return render_template("error.html", message="Internal server error. Please try again later.")

@app.route("/reroll/<firstname>", methods=["POST"])
def reroll(firstname):
    if not config["reroll_enabled"]:
        return render_template(
            "error.html",
            message="Rerolling is disabled. Contact admin for assistance."
        )

    firstname_lower = firstname.lower()
    if firstname_lower not in config["names"]:
        return render_template(
            "error.html",
            message=(
                "Oh no! Make sure you have spelled your name correctly. "
                f"Contact {config['admin_user']} if you believe there is a mistake."
            ),
        )

    try:
        # Remove the current assignment
        old_recipient = redis_client.get(f"recipient:{firstname_lower}")
        if old_recipient:
            redis_client.srem("assigned_recipients", old_recipient)

        # Get new available recipients
        all_names = set(config["names"])
        assigned_recipients = set(redis_client.smembers("assigned_recipients"))
        available_recipients = list(all_names - assigned_recipients - {firstname_lower})

        if not available_recipients:
            return render_template(
                "error.html",
                message="No available recipients left. Contact admin for assistance."
            )

        chosen_recipient = random.choice(available_recipients)

        # Assign the new recipient
        redis_client.set(f"recipient:{firstname_lower}", chosen_recipient)
        redis_client.sadd("assigned_recipients", chosen_recipient)

        return jsonify({"newName": chosen_recipient.capitalize()})

    except redis.RedisError as e:
        logging.error(f"Redis error: {e}")
        return render_template("error.html", message="Internal server error. Please try again later.")

if __name__ == "__main__":
    try:
        # Initialize the recipient assignments in Redis if not already done
        if not redis_client.exists("assigned_recipients"):
            redis_client.delete("assigned_recipients")  # Reset any existing data
            for name in config["names"]:
                redis_client.set(f"recipient:{name.lower()}", "")  # No recipient assigned initially

        app.run(host="0.0.0.0", debug=False, port=config["port"])
    except Exception as e:
        logging.critical(f"Failed to start the application: {e}")
