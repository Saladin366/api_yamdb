from django.urls import include, path
from rest_framework import routers

from .views import (
    create_token, create_user, myself, CategoryViewSet, CommentViewSet,
    GenreViewSet, ReviewViewSet, TitleViewSet, UserViewSet)

router = routers.DefaultRouter()
router.register('users', UserViewSet, basename='users')
router.register('categories', CategoryViewSet, basename='categories')
router.register('genres', GenreViewSet, basename='genres')
router.register('titles', TitleViewSet, basename='titles')
router.register(r'titles/(?P<title_id>\d+)/reviews',
                ReviewViewSet, basename='reviews')
router.register(
    r'titles/(?P<title_id>\d+)/reviews/(?P<review_id>\d+)/comments',
    CommentViewSet, basename='comments'
)

urlpatterns = [
    path('v1/users/me/', myself),
    path('v1/', include(router.urls)),
    path('v1/auth/signup/', create_user),
    path('v1/auth/token/', create_token),
]
