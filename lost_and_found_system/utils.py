import cv2
import numpy as np
from PIL import Image
from sklearn.metrics.pairwise import cosine_similarity
from sentence_transformers import SentenceTransformer
from transformers import BlipProcessor, BlipForConditionalGeneration
import torch
from .models import MatchedItem, LostItem, FoundItem, Notification
from .serializers import MatchedItemSerializer
import logging
import requests
from io import BytesIO
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from .models import ItemStatusChoices
import time
import os
import re


logger = logging.getLogger(__name__)

# Load the SentenceTransformer model
text_model = SentenceTransformer('all-MiniLM-L6-v2')

# Initialize image captioning model (only done once when module loads)
image_processor = None
image_captioning_model = None
yolo_model = None  # Initialize YOLOv8 model

def load_image_captioning_model():
    """
    Lazy-load the image captioning model when first needed.
    """
    global image_processor, image_captioning_model
    if image_processor is None or image_captioning_model is None:
        try:
            logger.info("Loading image captioning model...")
            image_processor = BlipProcessor.from_pretrained("Salesforce/blip-image-captioning-base")
            image_captioning_model = BlipForConditionalGeneration.from_pretrained("Salesforce/blip-image-captioning-base")
            logger.info("Image captioning model loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load image captioning model: {e}")
            # Fall back to existing methods if model fails to load
            return False
    return True

def load_yolo_model():
    """
    Lazy-load the YOLOv8 model when first needed.
    """
    global yolo_model
    if yolo_model is None:
        try:
            logger.info("Loading YOLOv8 model...")
            yolo_model = YOLO('yolov8n.pt')  # Load the smallest YOLOv8 model for efficiency
            logger.info("YOLOv8 model loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load YOLOv8 model: {e}")
            # Fall back to existing methods if model fails to load
            return False
    return True

def generate_image_caption(image_url):
    """
    Generate a textual description of an image using a pre-trained model.
    First detects and crops the main object using YOLOv8, then generates
    a caption for the cropped object using BLIP.
    
    Returns a tuple of:
    - Full caption (combined YOLOv8 label and BLIP description)
    - YOLOv8 object label
    """
    if not load_image_captioning_model():
        return "", ""
        
    try:
        # First detect and crop the main object
        cropped_image, object_label = detect_and_crop_object(image_url)
        
        if cropped_image is None:
            # If object detection failed, try the whole image
            logger.info("Object detection failed, using the whole image instead.")
            img_response = requests.get(image_url)
            cropped_image = Image.open(BytesIO(img_response.content)).convert('RGB')
        
        # Process image for the BLIP model
        inputs = image_processor(cropped_image, return_tensors="pt")
        
        # Generate caption
        outputs = image_captioning_model.generate(**inputs, max_length=30)
        blip_caption = image_processor.decode(outputs[0], skip_special_tokens=True)
        
        # Combine YOLOv8 label with BLIP caption if we have a label
        if object_label:
            full_caption = f"{object_label}: {blip_caption}"
        else:
            full_caption = blip_caption
        
        logger.info(f"Generated caption: '{full_caption}' (YOLO label: '{object_label}', BLIP: '{blip_caption}')")
        return full_caption, object_label
    except Exception as e:
        logger.error(f"Error generating image caption: {e}")
        return "", ""

def detect_and_crop_object(image_url):
    """
    Use YOLOv8 to detect the main object in an image and crop it.
    Returns the cropped image and the detected object label.
    """
    if not load_yolo_model():
        logger.error("YOLOv8 model not available")
        return None, ""

    try:
        # Download image from URL
        img_response = requests.get(image_url)
        img = Image.open(BytesIO(img_response.content)).convert('RGB')
        img_np = np.array(img)
        
        # Run YOLOv8 detection
        results = yolo_model(img_np)
        
        # Check if any objects were detected
        if len(results[0].boxes) == 0:
            logger.warning("No objects detected in image")
            return img, ""
        
        # Get the box with highest confidence
        boxes = results[0].boxes
        confidences = boxes.conf.cpu().numpy()
        best_box_idx = np.argmax(confidences)
        
        # Get the class label for the best box
        class_id = int(boxes.cls[best_box_idx])
        label = results[0].names[class_id]
        
        # Get coordinates for cropping (convert from xywh to xyxy)
        x1, y1, x2, y2 = boxes.xyxy[best_box_idx].cpu().numpy().astype(int)
        
        # Crop the image
        cropped_img = img.crop((x1, y1, x2, y2))
        logger.info(f"Detected object '{label}' with confidence {confidences[best_box_idx]:.2f}")
        
        return cropped_img, label
    except Exception as e:
        logger.error(f"Error detecting object: {e}")
        return None, ""

def calculate_text_similarity(text1, text2):
    """
    Calculate similarity between two texts using SentenceTransformer and cosine similarity.
    """
    embeddings = text_model.encode([text1, text2])
    similarity = cosine_similarity([embeddings[0]], [embeddings[1]])[0][0]
    return similarity

def calculate_image_similarity(image1_url, image2_url):
    """
    Calculate similarity between two images using OpenCV, considering both structural
    and color similarity.
    Accepts image URLs instead of file paths.
    """
    try:
        # Download images from URLs
        img1_response = requests.get(image1_url)
        img2_response = requests.get(image2_url)
        
        # Open images using Pillow from response content and keep color information
        img1_color = Image.open(BytesIO(img1_response.content))
        img2_color = Image.open(BytesIO(img2_response.content))
        
        # Also create grayscale versions for structural comparison
        img1_gray = img1_color.convert('L')
        img2_gray = img2_color.convert('L')

        # Resize all images to the same size
        size = (256, 256)
        img1_color = img1_color.resize(size)
        img2_color = img2_color.resize(size)
        img1_gray = img1_gray.resize(size)
        img2_gray = img2_gray.resize(size)

        # Convert images to numpy arrays
        img1_color_np = np.array(img1_color)
        img2_color_np = np.array(img2_color)
        img1_gray_np = np.array(img1_gray)
        img2_gray_np = np.array(img2_gray)
        
        # Compute structural similarity using grayscale images
        structural_score = cv2.matchTemplate(img1_gray_np, img2_gray_np, cv2.TM_CCOEFF_NORMED)
        structural_similarity = structural_score.max()
        
        # Compute color similarity using color histograms
        color_similarity = calculate_color_similarity(img1_color_np, img2_color_np)
        
        # Combine structural and color similarity (weighted combination)
        # Adjust weights based on importance (structural vs color)
        combined_similarity = 0.6 * structural_similarity + 0.4 * color_similarity
        
        logger.info(f"Image matching - Structural: {structural_similarity:.2f}, Color: {color_similarity:.2f}, Combined: {combined_similarity:.2f}")
        
        return combined_similarity
    except Exception as e:
        logger.error(f"Error calculating image similarity: {e}")
        return 0  # Return 0 if image comparison fails

def calculate_color_similarity(img1, img2):
    """
    Calculate color similarity between two images using color histograms.
    """
    try:
        # Convert from RGB to HSV color space (better for color comparison)
        img1_hsv = cv2.cvtColor(img1, cv2.COLOR_RGB2HSV)
        img2_hsv = cv2.cvtColor(img2, cv2.COLOR_RGB2HSV)
        
        # Define histogram parameters
        h_bins = 30  # Hue bins
        s_bins = 32  # Saturation bins
        hist_size = [h_bins, s_bins]
        # Hue ranges from 0 to 180, Saturation from 0 to 256 in OpenCV
        h_ranges = [0, 180]
        s_ranges = [0, 256]
        ranges = h_ranges + s_ranges
        channels = [0, 1]  # Use the H and S channels
        
        # Calculate histograms - properly include all required parameters
        hist1 = cv2.calcHist([img1_hsv], channels, None, hist_size, ranges)
        hist2 = cv2.calcHist([img2_hsv], channels, None, hist_size, ranges)
        
        # Normalize histograms
        cv2.normalize(hist1, hist1, alpha=0, beta=1, norm_type=cv2.NORM_MINMAX)
        cv2.normalize(hist2, hist2, alpha=0, beta=1, norm_type=cv2.NORM_MINMAX)
        
        # Compare histograms using correlation method
        # Returns a value between 0 and 1 (1 = perfect match)
        similarity = cv2.compareHist(hist1, hist2, cv2.HISTCMP_CORREL)
        
        return similarity
    except Exception as e:
        logger.error(f"Error calculating color similarity: {e}")
        return 0  # Return 0 if color comparison fails

def match_lost_and_found_items(lost_item: LostItem, found_item: FoundItem):
    """
    Match a lost item with a found item and create a MatchedItem entry if similarity is high.
    """
    logger.info(f"====== MATCHING PROCESS STARTED ======")
    logger.info(f"Comparing LostItem: {lost_item.name} (ID: {lost_item.item_id}) with FoundItem: {found_item.name} (ID: {found_item.item_id})")

    # Ensure the input objects are instances of LostItem and FoundItem
    if not isinstance(lost_item, LostItem) or not isinstance(found_item, FoundItem):
        logger.error("Invalid input: lost_item must be a LostItem and found_item must be a FoundItem.")
        raise ValueError("Invalid input: lost_item must be a LostItem and found_item must be a FoundItem.")

    # Log the original descriptions
    logger.info(f"Lost Item Description: \"{lost_item.name} {lost_item.description}\"")
    logger.info(f"Found Item Description: \"{found_item.name} {found_item.description}\"")

    # Calculate base text similarity from user-provided descriptions
    base_text_similarity = calculate_text_similarity(
        lost_item.name + " " + lost_item.description,
        found_item.name + " " + found_item.description
    )
    logger.info(f"BASE TEXT SIMILARITY: {base_text_similarity:.4f}")

    # Initialize variables for other similarity metrics
    caption_similarity = 0
    enhanced_text_similarity = 0
    
    if lost_item.image and found_item.image:
        logger.info("Both items have images. Performing image-based object detection and caption generation.")
        
        # Get captions and object labels from images using YOLOv8 and BLIP
        lost_caption, lost_object_label = generate_image_caption(lost_item.image)
        found_caption, found_object_label = generate_image_caption(found_item.image)
        
        logger.info(f"Lost Item AI Caption: \"{lost_caption}\"")
        logger.info(f"Found Item AI Caption: \"{found_caption}\"")
        logger.info(f"Lost Item Object Label: \"{lost_object_label}\"")
        logger.info(f"Found Item Object Label: \"{found_object_label}\"")
        
        # Calculate object label match similarity (1.0 if same, 0.0 if different)
        object_label_similarity = 1.0 if lost_object_label and found_object_label and lost_object_label.lower() == found_object_label.lower() else 0.0
        logger.info(f"OBJECT LABEL MATCH: {object_label_similarity:.1f}")
        
        if lost_caption and found_caption:
            # Calculate similarity between the captions
            caption_similarity = calculate_text_similarity(lost_caption, found_caption)
            logger.info(f"CAPTION-TO-CAPTION SIMILARITY: {caption_similarity:.4f}")
            
            # Create rich semantic context by combining:
            # 1. User-provided title and description
            # 2. YOLOv8 object labels
            # 3. BLIP-generated captions
            enhanced_lost_text = f"{lost_item.name} {lost_item.description} {lost_object_label} {lost_caption}"
            enhanced_found_text = f"{found_item.name} {found_item.description} {found_object_label} {found_caption}"
            
            logger.info(f"Enhanced Lost Item Description: \"{enhanced_lost_text}\"")
            logger.info(f"Enhanced Found Item Description: \"{enhanced_found_text}\"")
            
            # Calculate similarity using the enhanced text descriptions
            enhanced_text_similarity = calculate_text_similarity(enhanced_lost_text, enhanced_found_text)
            logger.info(f"ENHANCED TEXT SIMILARITY: {enhanced_text_similarity:.4f}")
            
            # Weighted average - giving more weight to enhanced similarity
            text_similarity = (base_text_similarity + 2 * enhanced_text_similarity) / 3
            logger.info(f"WEIGHTED TEXT SIMILARITY: {text_similarity:.4f}")
        else:
            logger.info("Couldn't generate captions for one or both images. Using only base text similarity.")
            text_similarity = base_text_similarity
    else:
        logger.info("One or both items do not have images. Using only text similarity.")
        text_similarity = base_text_similarity    # Calculate final similarity score with detailed weight breakdown
    if not lost_item.image or not found_item.image:
        # If no images, use only text similarity
        combined_similarity = text_similarity
        logger.info(f"FINAL SIMILARITY SCORE: {combined_similarity:.4f} (100% text similarity)")
    else:
        # With images, use a comprehensive weighted combination
        text_weight = 0.4  # Weight for text similarity (titles + descriptions)
        caption_weight = 0.3  # Weight for BLIP caption similarity
        object_label_weight = 0.3  # Weight for YOLOv8 object label match
        
        # Calculate weighted components
        text_component = text_weight * text_similarity
        caption_component = caption_weight * caption_similarity
        object_label_component = object_label_weight * object_label_similarity
        
        # Combine all components for final score
        combined_similarity = text_component + caption_component + object_label_component
        
        logger.info(f"SIMILARITY COMPONENTS:")
        logger.info(f"- Text Similarity: {text_similarity:.4f} × {text_weight} = {text_component:.4f}")
        logger.info(f"- Caption Similarity: {caption_similarity:.4f} × {caption_weight} = {caption_component:.4f}")
        logger.info(f"- Object Label Match: {object_label_similarity:.1f} × {object_label_weight} = {object_label_component:.4f}")
        logger.info(f"FINAL SIMILARITY SCORE: {combined_similarity:.4f}")

    # Create a MatchedItem if similarity exceeds threshold
    threshold = 0.6  # Threshold for matching
    logger.info(f"Match threshold: {threshold}")
    
    if combined_similarity > threshold:
        logger.info(f"✅ MATCH FOUND! Score {combined_similarity:.4f} exceeds threshold {threshold}")
        matched_item_data = {
            "lost_item": lost_item.item_id,
            "found_item": found_item.item_id,
            "similarity_score": combined_similarity * 100,  
            "status": MatchedItem.MatchingResult.FAILED
        }
        serializer = MatchedItemSerializer(data=matched_item_data)
        if serializer.is_valid():
            matched_item = serializer.save()
            logger.info(f"MatchedItem created with ID: {matched_item.match_id}")
            logger.info(f"====== MATCHING PROCESS COMPLETED ======")
            return matched_item
        else:
            logger.error(f"Failed to create MatchedItem: {serializer.errors}")
    else:
        logger.info(f"❌ NO MATCH FOUND. Score {combined_similarity:.4f} below threshold {threshold}")
    
    logger.info(f"====== MATCHING PROCESS COMPLETED ======")
    return None

def send_and_save_notification(user, title, message, match_id=None):
    """
    Utility function to send a WebSocket notification and save it to the database.
    
    Args:
        user: The user to send the notification to
        title: The notification title
        message: The notification message body
        match_id: Optional match_id to include in the notification
    """
    # Create database record
    notification_data = {
        'user': user,
        'message': message,
        'is_read': False
    }
    
    # If match_id provided, get the MatchedItem and include it
    matched_item = None
    if match_id is not None:
        try:
            matched_item = MatchedItem.objects.get(match_id=match_id)
            notification_data['matched_item'] = matched_item
        except MatchedItem.DoesNotExist:
            logger.warning(f"Tried to associate notification with non-existent match_id {match_id}")
    
    notification = Notification.objects.create(**notification_data)
    
    # Send real-time WebSocket notification
    channel_layer = get_channel_layer()
    group_name = f"user_{user.id}" if user.is_authenticated else "anonymous"
    
    notification_data_ws = { # Renamed to avoid conflict
        "type": "send_notification",
        "message": {"title": title, "body": message, "matched_item_id": match_id}
    }
    
    logger.info(f"Sending notification to {user.email}: {title} - {message}")
    async_to_sync(channel_layer.group_send)(group_name, notification_data_ws)
    
    return notification

def check_description_relevance(item_name, description):
    """
    Uses a Hugging Face model to check if the description is relevant to the item name.
    Returns 'relevant', 'irrelevant', or 'api_error'.
    """
    try:
        hf_api_key = os.environ.get("HUGGINGFACE_API_KEY")
        if not hf_api_key:
            logger.error("HUGGINGFACE_API_KEY environment variable not set.")
            return "api_error"

        api_url = "https://router.huggingface.co/novita/v3/openai/chat/completions"
        headers = {
            "Authorization": f"Bearer {hf_api_key}",
            "Content-Type": "application/json"
        }
        
        prompt_text = (
            f"Analyze the following item and its description. Based *only* on whether the description accurately describes the item itself (like its appearance, color, brand, or specific features), "
            f"and not about where/when it was lost/found or if the description is generic, "
            f"reply with a single word: 'relevant' if the description is about the item's characteristics, or 'irrelevant' otherwise.\\n\\n"
            f"Item Name: '{item_name}'\\n"
            f"Description: '{description}'\\n\\n"
            f"Your one-word answer:"
        )

        payload = {
            "model": "deepseek/deepseek-v3-0324",
            "messages": [{"role": "user", "content": prompt_text}],
            "max_tokens": 5, # Max length for 'relevant' or 'irrelevant'
            "temperature": 0.1 # Low temperature for deterministic output
        }
        
        max_retries = 3
        last_exception = None # To store the last exception for logging if all retries fail

        for attempt in range(max_retries):
            response_obj = None # To ensure response_obj is defined for logging in HTTPError
            try:
                response_obj = requests.post(api_url, headers=headers, json=payload, timeout=10)
                response_obj.raise_for_status()  # Will raise an HTTPError for bad responses (4xx or 5xx)
                result = response_obj.json()
                last_exception = None # Clear last exception on successful request processing
                
                # Robust check for the expected response structure
                if result.get("choices") and \
                   isinstance(result["choices"], list) and \
                   len(result["choices"]) > 0 and \
                   result["choices"][0].get("message") and \
                   isinstance(result["choices"][0]["message"], dict) and \
                   "content" in result["choices"][0]["message"]:
                    
                    answer = result["choices"][0]["message"]["content"].strip().lower()
                    
                    if answer == "relevant": # Strict check
                        logger.info(f"Hugging Face API response: '{answer}' -> relevant")
                        return "relevant"
                    elif answer == "irrelevant": # Strict check
                        logger.info(f"Hugging Face API response: '{answer}' -> irrelevant")
                        return "irrelevant"
                    else:
                        # Model returned something other than 'relevant' or 'irrelevant'
                        logger.warning(f"Hugging Face API returned ambiguous answer: '{answer}' on attempt {attempt+1}/{max_retries}.")
                        # This attempt is considered failed, will proceed to retry logic below.
                
                else: # Unexpected response structure
                    logger.warning(f"Hugging Face API response structure unexpected on attempt {attempt+1}/{max_retries}: {result}")
                    # This attempt is considered failed, will proceed to retry logic below.

            except requests.exceptions.HTTPError as e:
                last_exception = e
                logger.warning(f"Hugging Face API HTTP error on attempt {attempt+1}/{max_retries}: {e}")
                # Check if response_obj is available (it should be if raise_for_status() was called)
                if hasattr(e, 'response') and e.response is not None and e.response.status_code == 429:
                    wait_time = (2 ** attempt) * 2  # Exponential backoff: 2, 4, 8 seconds
                    logger.info(f"Rate limited. Waiting {wait_time} seconds before retry.")
                    time.sleep(wait_time)
                    continue  # Continue to the next attempt
                # For other HTTP errors, fall through to generic retry wait
            
            except requests.exceptions.RequestException as e: # Catches DNS errors, connection timeouts, etc.
                last_exception = e
                logger.warning(f"Hugging Face API request error on attempt {attempt+1}/{max_retries}: {e}")
                # Fall through to generic retry wait
            
            except Exception as e: # Catch any other unexpected errors (e.g., JSONDecodeError)
                last_exception = e
                logger.error(f"Unexpected error during Hugging Face API call processing attempt {attempt+1}/{max_retries}: {e}")
                # Fall through to generic retry wait

            # If this was the last attempt and we haven't returned a definitive answer
            if attempt == max_retries - 1:
                logger.error(f"All {max_retries} attempts failed or yielded no definitive answer. Last error/issue: {last_exception if last_exception else 'Ambiguous or malformed response'}")
                break # Exit loop, will fall through to return "api_error"
            
            # Generic wait for the next retry, if not a 429 (which has its own 'continue' statement)
            # This wait applies if the response was ambiguous, structure was wrong, or a non-429 HTTP/Request error occurred.
            
            # Check if the last exception was a 429 to avoid double waiting
            is_429 = isinstance(last_exception, requests.exceptions.HTTPError) and \
                      hasattr(last_exception, 'response') and \
                      last_exception.response is not None and \
                      last_exception.response.status_code == 429
            
            if not is_429:
                wait_time = (2 ** attempt) * 1 # Exponential backoff: 1, 2 seconds (for the first two retries)
                logger.info(f"Waiting {wait_time} seconds before next retry (attempt {attempt+2}/{max_retries}).")
                time.sleep(wait_time)

        # If loop finished without returning "relevant" or "irrelevant" (i.e., all retries exhausted)
        logger.warning("Hugging Face API calls exhausted or consistently failed to provide a clear answer. Defaulting to api_error.")
        return "api_error"

    except Exception as e: # Catch errors in the setup before the loop (e.g. critical error not related to API call itself)
        logger.error(f"Critical error in relevance check function's outer scope: {e}")
        return "api_error"
