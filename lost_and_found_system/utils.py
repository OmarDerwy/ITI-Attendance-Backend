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


logger = logging.getLogger(__name__)

# Load the SentenceTransformer model
text_model = SentenceTransformer('all-MiniLM-L6-v2')

# Initialize image captioning model (only done once when module loads)
image_processor = None
image_captioning_model = None

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

def generate_image_caption(image_url):
    """
    Generate a textual description of an image using a pre-trained model.
    """
    if not load_image_captioning_model():
        return ""
        
    try:
        # Download image from URL
        img_response = requests.get(image_url)
        image = Image.open(BytesIO(img_response.content)).convert('RGB')
        
        # Process image for the model
        inputs = image_processor(image, return_tensors="pt")
        
        # Generate caption
        outputs = image_captioning_model.generate(**inputs, max_length=30)
        caption = image_processor.decode(outputs[0], skip_special_tokens=True)
        
        logger.info(f"Generated caption for image: '{caption}'")
        return caption
    except Exception as e:
        logger.error(f"Error generating image caption: {e}")
        return ""

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
    image_similarity = 0
    
    if lost_item.image and found_item.image:
        logger.info("Both items have images. Performing image-based similarity calculations.")
        
        # Get captions from images
        lost_caption = generate_image_caption(lost_item.image)
        found_caption = generate_image_caption(found_item.image)
        
        logger.info(f"Lost Item AI Caption: \"{lost_caption}\"")
        logger.info(f"Found Item AI Caption: \"{found_caption}\"")
        
        if lost_caption and found_caption:
            # Calculate similarity between the captions
            caption_similarity = calculate_text_similarity(lost_caption, found_caption)
            logger.info(f"CAPTION-TO-CAPTION SIMILARITY: {caption_similarity:.4f}")
            
            # Optionally enhance the original descriptions with captions
            enhanced_lost_text = f"{lost_item.name} {lost_item.description} {lost_caption}"
            enhanced_found_text = f"{found_item.name} {found_item.description} {found_caption}"
            
            logger.info(f"Enhanced Lost Item Description: \"{enhanced_lost_text}\"")
            logger.info(f"Enhanced Found Item Description: \"{enhanced_found_text}\"")
            
            enhanced_text_similarity = calculate_text_similarity(enhanced_lost_text, enhanced_found_text)
            logger.info(f"ENHANCED TEXT SIMILARITY: {enhanced_text_similarity:.4f}")
            
            # Use enhanced similarity if available
            text_similarity = (base_text_similarity + enhanced_text_similarity) / 2
            logger.info(f"AVERAGED TEXT SIMILARITY: {text_similarity:.4f}")
        else:
            logger.info("Couldn't generate captions for one or both images. Using only base text similarity.")
            text_similarity = base_text_similarity
            
        # Also calculate direct visual similarity as a backup/complement
        logger.info("Calculating direct image similarity (structural + color)...")
        image_similarity = calculate_image_similarity(lost_item.image, found_item.image)
        logger.info(f"DIRECT IMAGE SIMILARITY: {image_similarity:.4f}")
    else:
        logger.info("One or both items do not have images. Using only text similarity.")
        text_similarity = base_text_similarity

    # Calculate final similarity score with detailed weight breakdown
    if not lost_item.image or not found_item.image:
        # If no images, use only text similarity
        combined_similarity = text_similarity
        logger.info(f"FINAL SIMILARITY SCORE: {combined_similarity:.4f} (100% text similarity)")
    else:
        # With images, use a weighted combination of all similarities
        # Adjust weights based on what proves most effective for your use case
        text_weight = 0.5
        caption_weight = 0.3
        image_weight = 0.2
        
        text_component = text_weight * text_similarity
        caption_component = caption_weight * caption_similarity
        image_component = image_weight * image_similarity
        
        combined_similarity = text_component + caption_component + image_component
        
        logger.info(f"SIMILARITY COMPONENTS:")
        logger.info(f"- Text Similarity: {text_similarity:.4f} × {text_weight} = {text_component:.4f}")
        logger.info(f"- Caption Similarity: {caption_similarity:.4f} × {caption_weight} = {caption_component:.4f}")
        logger.info(f"- Image Similarity: {image_similarity:.4f} × {image_weight} = {image_component:.4f}")
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
    
    notification_data = {
        "type": "send_notification",
        "message": {
            "title": title,
            "body": message,
            "matched_item_id": match_id  # Changed from notification_id to matched_item_id
        }
    }
    
    logger.info(f"Sending notification to {user.email}: {title} - {message}")
    async_to_sync(channel_layer.group_send)(group_name, notification_data)
    
    return notification
