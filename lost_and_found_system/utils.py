import cv2
import numpy as np
from PIL import Image
from sklearn.metrics.pairwise import cosine_similarity
from sentence_transformers import SentenceTransformer
from .models import MatchedItem, LostItem, FoundItem
from .serializers import MatchedItemSerializer
import logging

logger = logging.getLogger(__name__)

# Load the SentenceTransformer model
text_model = SentenceTransformer('all-MiniLM-L6-v2')

def calculate_text_similarity(text1, text2):
    """
    Calculate similarity between two texts using SentenceTransformer and cosine similarity.
    """
    embeddings = text_model.encode([text1, text2])
    similarity = cosine_similarity([embeddings[0]], [embeddings[1]])[0][0]
    return similarity

def calculate_image_similarity(image1_path, image2_path):
    """
    Calculate similarity between two images using OpenCV and structural similarity.
    """
    try:
        # Open images using Pillow
        img1 = Image.open(image1_path).convert('L')  # Convert to grayscale
        img2 = Image.open(image2_path).convert('L')

        # Resize images to the same size
        img1 = img1.resize((256, 256))
        img2 = img2.resize((256, 256))

        # Convert images to numpy arrays
        img1 = np.array(img1)
        img2 = np.array(img2)

        # Compute structural similarity
        score = cv2.matchTemplate(img1, img2, cv2.TM_CCOEFF_NORMED)
        return score.max()
    except Exception as e:
        logger.error(f"Error calculating image similarity: {e}")
        return 0  # Return 0 if image comparison fails

def match_lost_and_found_items(lost_item: LostItem, found_item: FoundItem):
    """
    Match a lost item with a found item and create a MatchedItem entry if similarity is high.
    """
    logger.info(f"Starting matching process for LostItem: {lost_item.name} and FoundItem: {found_item.name}")

    # Ensure the input objects are instances of LostItem and FoundItem
    if not isinstance(lost_item, LostItem) or not isinstance(found_item, FoundItem):
        logger.error("Invalid input: lost_item must be a LostItem and found_item must be a FoundItem.")
        raise ValueError("Invalid input: lost_item must be a LostItem and found_item must be a FoundItem.")

    # Calculate text similarity
    text_similarity = calculate_text_similarity(
        lost_item.name + " " + lost_item.description,
        found_item.name + " " + found_item.description
    )
    logger.info(f"Text similarity between '{lost_item.name}' and '{found_item.name}': {text_similarity:.2f}")

    # Calculate image similarity if both items have images
    image_similarity = 0
    if lost_item.image and found_item.image:
        image_similarity = calculate_image_similarity(
            lost_item.image.path, found_item.image.path
        )
        logger.info(f"Image similarity between '{lost_item.name}' and '{found_item.name}': {image_similarity:.2f}")
    else:
        logger.info(f"One or both items do not have images. Using only text similarity.")

    # If no images are provided, rely entirely on text similarity
    if not lost_item.image or not found_item.image:
        combined_similarity = text_similarity
    else:
        # Combine text and image similarity
        combined_similarity = (0.7 * text_similarity) + (0.3 * image_similarity)

    logger.info(f"Combined similarity score: {combined_similarity:.2f}")

    # Create a MatchedItem if similarity exceeds threshold
    if combined_similarity > 0.6:  # Threshold for matching
        matched_item_data = {
            "lost_item": lost_item.item_id,
            "found_item": found_item.item_id,
            "similarity_score": combined_similarity * 100,  # Convert to percentage
            "status": MatchedItem.MatchingResult.FAILED
        }
        serializer = MatchedItemSerializer(data=matched_item_data)
        if serializer.is_valid():
            matched_item = serializer.save()
            logger.info(f"MatchedItem created: {matched_item}")
            return matched_item
        else:
            logger.error(f"Failed to create MatchedItem: {serializer.errors}")

    logger.info("No match found. Combined similarity score did not exceed the threshold.")
    return None
