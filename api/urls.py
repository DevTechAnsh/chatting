from rest_framework.routers import DefaultRouter
from django.conf.urls import *

from .views import (
    ComplaintViewSet, ChatOpinionConversationViewSet, ChatOpinionViewSet,AcceptChatOpinionCase,
    CompletedChatOpinionCase
)

app_name = 'chatting_api'

router = DefaultRouter()
router.register('chat-opinion', ChatOpinionViewSet, basename='chat-opinion')
router.register('complaint', ComplaintViewSet, basename='complaint')
router.register('chat', ChatOpinionConversationViewSet, basename='chat')

urlpatterns = router.urls

urlpatterns +=[
    url(r'^chat-opinion/(?P<pk>[0-9]+)/accept/$',AcceptChatOpinionCase.as_view(),
    name='Chat-opinion-accept'),
    url(r'^chat-opinion/(?P<pk>[0-9]+)/completed/$',CompletedChatOpinionCase.as_view(),
    name='chat-opinion-complete'),
]
