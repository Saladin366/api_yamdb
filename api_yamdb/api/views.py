from django.contrib.sites.shortcuts import get_current_site
from django.contrib.auth.base_user import BaseUserManager
from django.core.mail import EmailMessage
from django.db.models import Avg
from django.shortcuts import get_object_or_404
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework import viewsets, filters, serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken

from users.models import User
from .permissions import IsAdmin, IsAdminOrReadOnly, CommentReviewPermission
from .serializers import CategorySerializer, GenreSerializer, TitleSerializer
from reviews.models import Category, Genre, Title, Review
from .serializers import (CreateUserSerializer, UsersSerializer,
                          TokenSerializer, CommentSerializer, ReviewSerializer)

BAD_CONFIRMATION_CODE = 'Это поле некорректно'
MAIL_SUBJECT = 'Ваш confirmation code'


@api_view(['POST'])
def create_user(request):
    """Создаёт нового или получает из базы ранее созданного пользователя и
       высылает код для получения токена на почту.
    """
    serializer = CreateUserSerializer(data=request.data)
    email = serializer.initial_data.get('email', None)
    username = serializer.initial_data.get('username', None)
    if (serializer.is_valid() or User.objects.filter(username=username,
                                                     email=email).exists()):
        user, created = User.objects.get_or_create(
            email=email, username=username)
        user.set_password(BaseUserManager().make_random_password())
        user.save()
        current_site = get_current_site(request).domain
        email_for_user = EmailMessage(MAIL_SUBJECT, user.password,
                                      current_site, [email])
        email_for_user.send()
        return Response(serializer.data, status=status.HTTP_200_OK)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
def create_token(request):
    """Создаёт токен для пользователя."""
    serializer = TokenSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    username = serializer.data['username']
    user = get_object_or_404(User, username=username)
    confirmation_code = serializer.data['confirmation_code']
    if confirmation_code == user.password:
        token = RefreshToken.for_user(user).access_token
        data = {'token': str(token)}
        return Response(data, status=status.HTTP_200_OK)
    data = {'confirmation_code': BAD_CONFIRMATION_CODE}
    return Response(data, status=status.HTTP_400_BAD_REQUEST)


class UserViewSet(mixins.CreateModelMixin, mixins.ListModelMixin,
                  viewsets.GenericViewSet):
    """ViewSet для создания нового или получения списка пользователей."""
    queryset = User.objects.all()
    serializer_class = UsersSerializer
    permission_classes = [IsAdmin]
    pagination_class = PageNumberPagination


@api_view(['GET', 'PATCH'])
@permission_classes([IsAuthenticated])
def myself(request):
    """Позволяет пользователю получить или изменить информацию о себе."""
    user = request.user
    if request.method == 'GET':
        serializer = UsersSerializer(user)
        return Response(serializer.data)
    serializer = UsersSerializer(user, data=request.data, partial=True)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    if user.role != 'admin':
        serializer.save(role=user.role)
    else:
        serializer.save()
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(['GET', 'PATCH', 'DELETE'])
@permission_classes([IsAdmin])
def admin_get_user(request, username):
    """Позволяет администратору получить, изменить или удалить пользователя."""
    user = get_object_or_404(User, username=username)
    if request.method == 'GET':
        serializer = UsersSerializer(user)
        return Response(serializer.data)
    if request.method == 'DELETE':
        user.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
    serializer = UsersSerializer(user, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class CategoryViewSet(viewsets.ModelViewSet):
    filter_backends = (filters.SearchFilter,)
    search_fields = ('name',)
    pagination_class = PageNumberPagination
    serializer_class = CategorySerializer
    queryset = Category.objects.all()
    permission_classes = [IsAdminOrReadOnly]


class GenreViewSet(viewsets.ModelViewSet):
    filter_backends = (filters.SearchFilter,)
    search_fields = ('name',)
    pagination_class = PageNumberPagination
    serializer_class = GenreSerializer
    queryset = Genre.objects.all()
    permission_classes = [IsAdminOrReadOnly]


class TitleViewSet(viewsets.ModelViewSet):
    filter_backends = (filters.SearchFilter,)
    search_fields = ('category', 'genre', 'name', 'year')
    pagination_class = PageNumberPagination
    serializer_class = TitleSerializer
    queryset = Title.objects.all()
    permission_classes = [IsAdminOrReadOnly]


class ReviewViewSet(viewsets.ModelViewSet):
    serializer_class = ReviewSerializer
    pagination_class = PageNumberPagination
    permission_classes = [CommentReviewPermission]

    def update_rating(self, title):
        reviews = title.reviews.all()
        sums = reviews.aggregate(Avg("score"))
        title.rating = int(sums['score__avg'])
        title.save()

    def get_title(self):
        title_id = self.kwargs.get('title_id')
        title = get_object_or_404(Title, id=title_id)
        return title

    def perform_update(self, serializer):
        title = self.get_title()
        serializer.save()
        self.update_rating(title)

    def perform_destroy(self, instance):
        title = self.get_title()
        instance.delete()
        self.update_rating(title)

    def perform_create(self, serializer):
        title = self.get_title()
        author = self.request.user
        if Review.objects.filter(author=author, title=title).exists():
            raise serializers.ValidationError()
        serializer.save(author=self.request.user, title=title)
        self.update_rating(title)

    def get_queryset(self):
        title = self.get_title()
        return title.reviews.all()


class CommentViewSet(viewsets.ModelViewSet):
    serializer_class = CommentSerializer
    pagination_class = PageNumberPagination
    permission_classes = [CommentReviewPermission]

    def perform_create(self, serializer):
        review_id = self.kwargs.get('review_id')
        review = get_object_or_404(Review, id=review_id)
        serializer.save(author=self.request.user, review=review)

    def get_queryset(self):
        review_id = self.kwargs.get('review_id')
        review = get_object_or_404(Review, id=review_id)
        return review.comments.all()
