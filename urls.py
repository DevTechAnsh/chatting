from django.conf.urls import *

from . import views

app_name = 'Chat_opinion'

urlpatterns = [
    url(r'^$', views.DoctorListingView.as_view(), name='doctors'),
    url(r'case-details/(?P<slug>[\w-]+)/$', views.CaseDetailView.as_view(),
        name='case_detail'),
    url(r'conversation-replay/(?P<pk>[0-9]+)/$',
        views.ConversationsReplayView.as_view(), name='conversation_replay'),

    url(r'complaint/(?P<pk>[0-9]+)/$', views.ComplaintView.as_view(),
        name='conversation_complaint')
]
