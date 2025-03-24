from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import LostItemViewSet, FoundItemViewSet, MatchedItemViewSet

router = DefaultRouter()
router.register(r'lost-items', LostItemViewSet, basename='lostitem')
router.register(r'found-items', FoundItemViewSet, basename='founditem')
router.register(r'matched-items', MatchedItemViewSet, basename='matcheditem')

urlpatterns = [
    path('', include(router.urls)),
]
