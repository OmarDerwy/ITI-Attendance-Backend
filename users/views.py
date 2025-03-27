import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from svix import Webhook, WebhookVerificationError
import dotenv
import os
import logging
import clerk_backend_api
from .models import CustomUser
from .helpers import getGroupIDFromNames

logging.basicConfig(level=logging.INFO)
dotenv.load_dotenv()

# Replace this with your Clerk webhook signing secret
CLERK_WEBHOOK_SECRET = os.getenv("CLERK_WEBHOOK_SECRET")

@csrf_exempt
def clerk_webhook(request):
    if request.method != "POST":
        return JsonResponse({"error": "Invalid HTTP method"}, status=405)
    
    if not CLERK_WEBHOOK_SECRET or not os.getenv("CLERK_SECRET_KEY"):
        return JsonResponse({"error": "Missing required environment variables"}, status=500)

    clerk = clerk_backend_api.Clerk(os.getenv("CLERK_SECRET_KEY"))
    try:
        # Parse the webhook payload
        payload = request.body
        
        headers = {key: value for key, value in request.headers.items()}

        # Verify the webhook signature
        webhook = Webhook(CLERK_WEBHOOK_SECRET)
        event = webhook.verify(payload, headers)

        # Process the event
        if event["type"] == "user.created":
            # Handle user creation
            user_data = event["data"]
            logging.info(f"Processing event: {event['type']} for user ID: {user_data.get('id')}")
            clerk.users.update(user_id=user_data["id"], public_metadata={"roles": ["student"]})
            try:
                CustomUser.objects.create(email=user_data["email_addresses"][0]["email_address"], clerk_user_id=user_data["id"])
            except Exception as e:
                logging.error(f"Error creating user: {str(e)}")
                return JsonResponse({"error": "Failed to create user"}, status=500)
            # Add your logic here (e.g., create a user in your database)
        elif event["type"] == "user.updated":
            # Handle user updates
            user_data: dict = event["data"]
            logging.info(f"Processing event: {event['type']} for user ID: {user_data.get('id')}")
            try:
                user = CustomUser.objects.get(clerk_user_id=user_data["id"])
                user.email = user_data["email_addresses"][0]["email_address"]
                user.first_name = user_data["first_name"]
                user.last_name = user_data["last_name"]
                user.last_login = user_data["last_sign_in_at"]
                public_metadata: dict = user_data.get("public_metadata", {})
                role: list = public_metadata.get("roles", ["student"])
                group_ids = getGroupIDFromNames(role)
                user.groups.clear()
                user.groups.set(group_ids)
                user.save()
            except CustomUser.DoesNotExist as e:
                logging.error(f"User not found: {str(e)}")
                return JsonResponse({"error": "User not found"}, status=404)
                
            # Add your logic here
        elif event["type"] == "user.deleted":
            # Handle user deletion
            user_data = event["data"]
            logging.info(f"Processing event: {event['type']} for user ID: {user_data.get('id')}")
            try:
                user = CustomUser.objects.get(clerk_user_id=user_data["id"])
                user.delete()
            except CustomUser.DoesNotExist as e:
                logging.error(f"User not found: {str(e)}")
                return JsonResponse({"error": "User not found"}, status=404)
            # Add your logic here

        return JsonResponse({"status": "success", "message": "Webhook received successfully"}, status=200)
    except WebhookVerificationError as e:
        return JsonResponse({"error": "Invalid webhook signature"}, status=400)
    except CustomUser.DoesNotExist as e:
        return JsonResponse({"error": "User not found"}, status=404)
    except Exception as e:
        logging.error(f"Unexpected error: {str(e)}")
        return JsonResponse({"error": "An unexpected error occurred. Please try again later."}, status=400)
