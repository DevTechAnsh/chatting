from django.utils.translation import gettext_lazy as _
from rest_framework.mixins import CreateModelMixin, ListModelMixin
from rest_framework.permissions import IsAuthenticated
from rest_framework.serializers import ValidationError
from rest_framework.viewsets import GenericViewSet
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import mixins
from django.db.models import Q
from django.db.models import Count, Max
from django.http import Http404
from notification.models import Notification
from .serializers import ComplaintSerializer, ConversationSerializer
from .serializers import ChatOpinionSerializer
from ..models import Complaint, ChatOpinionConversation
from booking.models import booking

from core.choices import (
    CANCEL, COMPLETE, IN_PROGRESS, RESCHEDULED, CREDIT,
    DOCTOR, UPCOMING, NO_SHOW, CANCELLED, CASE_ACCEPTED, CASE_COMPLETED
)

from rest_framework.status import (
    HTTP_400_BAD_REQUEST,
    HTTP_404_NOT_FOUND,
    HTTP_200_OK,
    HTTP_204_NO_CONTENT
)


class ComplaintViewSet(CreateModelMixin, GenericViewSet):
    """
        API endpoint for Chat-Opinion Complaint

        * /api/v1/complaint/

        ** POST Request **

            {
                "description": "Testing APIS",
                "booking": "13"  <---- booking id
            }

        **returns:**

            {
                "id": 3,
                "description": "Testing APIS",
                "booking": 13
            }
    """
    permission_classes = (IsAuthenticated,)
    serializer_class = ComplaintSerializer
    queryset = Complaint.objects.all()


class ChatOpinionConversationViewSet(ListModelMixin, CreateModelMixin,
                                       GenericViewSet):
    """
        API endpoint for Chat-Opinion Chat

        * /api/v1/chat/?booking=15

            ** GET Request **

                {
                    "id": 27,
                    "patient_can_replay": false,
                    "created": "2020-01-17T10:11:23.185706+03:00",
                    "is_doctor_message": false,
                    "message": "hello",
                    "patient": 1,
                    "doctor": 6,
                    "booking": 15,
                    "doctor_attachments": [
                                            {
                                                "name": "ReportFile1.Png",
                                                "attachment": "http://127.0.0.1:8000/media/documents/file1.png.png"
                                            }
                                        ],
                    "patient_attachments": [
                                            {
                                                "name": "Report.Png",
                                                "attachment": "http://127.0.0.1:8000/media/documents/file1.png.png"
                                            }
                                        ],
                }

        * /api/v1/chat/

            ** POST Request **

                {
                    "patient": 1,
                    "doctor": 6,
                    "booking": 15,
                    "message": "hello",
                    "files": [
                                {
                                    "file1.png": "bas64content",
                                    "file2.pdf": "bas64content",
                                }
                            ]
                }

            **returns:**

                {
                    "id": 27,
                    "patient_can_replay": false,
                    "created": "2020-01-17T10:11:23.185706+03:00",
                    "is_doctor_message": false,
                    "message": "hello",
                    "patient": 1,
                    "doctor": 6,
                    "booking": 15,
                }

            ** if maximum replies limit reached.

                {
                    "message": [
                        "Maximum Replies limit is 3"
                    ]
                }
        """
    serializer_class = ConversationSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None
    queryset = ChatOpinionConversation.objects.all()

    def get_queryset(self):
        booking = self.request.GET.get('booking', None)
        if not booking:
            raise ValidationError(
                {"no_field_error": [_('Please Provide booking id')]}
            )
        qs = super(ChatOpinionConversationViewSet, self).get_queryset()
        user = self.request.user
        if self.request.user.is_doctor:
            qs = qs.filter(doctor__user=user)
        else:
            qs = qs.filter(patient__parent=user)
        qs = qs.filter(booking__id=booking)
        # mark as read doctor messages
        doctor_conversation_ids = qs.filter(
            is_doctor_message=True).values_list('notification_id')
        doctor_notifications = Notification.objects.filter(
            id__in=doctor_conversation_ids, is_read=False)
        for elem in doctor_notifications:
            elem.is_read = True
            elem.save()
        return qs


class ChatOpinionViewSet(mixins.ListModelMixin,
                           GenericViewSet):

    """
    Endpoint to Retrieve, Update booking

    **GET (List): /api/v1/Chat-opinion/**

        {
            "id": 1792,
            "status": "in-progress",
            "status_display": "In Progress",    
            "hospitals": []
            },
            "creation_time": "12:12 PM",
            "creation_date": "Feb 23, 2021"
        }
    """

    serializer_class = ChatOpinionSerializer
    queryset = booking.objects.filter(service_type__slug="Chat-opinion")
    permission_classes = [IsAuthenticated]

    def list(self, request, *args, **kwargs):
        # override to pass user into serializer
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(
                page, many=True, user=request.user)
            data = self.get_paginated_response(serializer.data)
            data["count_new"] = self.get_Chat_opinion_queryset(
                "new", self.get_queryset()).count()
            data["count_in_progress"] = self.get_Chat_opinion_queryset(
                "in-progress", self.get_queryset()).count()
            data["count_reply"] = self.get_Chat_opinion_queryset(
                "reply", self.get_queryset()).count()
            return Response(data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def retrieve(self, request, *args, **kwargs):
        # override to allow guest user booking to get booking details
        queryset = self.get_queryset()
        instance = queryset.get(id=self.kwargs.get("pk", None))
        if not instance.is_guest and instance.patient.parent:
            self.permission_classes = [IsAuthenticated]
        serializer = self.get_serializer(instance, user=request.user)
        return Response(serializer.data)

    def filter_queryset(self, queryset):
        status = self.request.GET.get("status", None)
        return self.get_Chat_opinion_queryset(status, queryset) if status else queryset.filter(status=status)

    def get_Chat_opinion_queryset(self, status, queryset):
        status = "in-progress" if status in ["in-progress"] else status
        if status == "closed":
            return queryset.filter(Q(status="completed") | Q(status="cancelled"))
        elif status == 'in-progress':
            doctor_queryset = queryset.filter(
                status="in-progress").annotate(conv_id=Max('booking_conversation__id'))
            sc_id = doctor_queryset.values_list('conv_id')
            doctor_booking_id = ChatOpinionConversation.objects.filter(
                id__in=sc_id, is_doctor_message=True).values_list('booking_id')
            return queryset.filter(id__in=doctor_booking_id)
        elif status == 'reply':
            queryset = queryset.filter(
                status="in-progress").annotate(conv_id=Max('booking_conversation__id'))
            sc_id = queryset.values_list('conv_id')
            booking_id = ChatOpinionConversation.objects.filter(
                id__in=sc_id, is_doctor_message=False).values_list('booking_id')
            idle_booking_id = queryset.filter(
                status="in-progress", booking_conversation__id=None).values_list('id')
            return queryset.filter(Q(id__in=booking_id) | Q(id__in=idle_booking_id))
        else:
            return queryset.filter(status=status) if status else queryset

    def get_queryset(self):
        qs = super(ChatOpinionViewSet, self).get_queryset()
        if self.request.user.is_authenticated and not self.request.user.is_doctor:
            return qs.filter(user=self.request.user)
        elif self.request.user.is_authenticated and self.request.user.is_doctor:
            return qs.filter(doctor__user=self.request.user)
        return qs


class AcceptChatOpinionCase(APIView):

    permission_classes = [IsAuthenticated]

    def get_object(self, pk):
        try:
            return booking.objects.get(pk=pk)
        except booking.DoesNotExist:
            raise Http404

    def post(self, request, pk, format=None):
        booking = self.get_object(pk=pk)
        if self.request.user.is_authenticated and self.request.user.is_doctor:
            doctor = self.request.user.doctor
            if booking.doctor == doctor:
                booking.status = IN_PROGRESS
                booking.save()
                serializer = ChatOpinionSerializer(
                    booking, user=request.user)
                return Response(serializer.data)
            else:
                return Response({'message': 'You are not authorized to accept this booking'}, status=HTTP_400_BAD_REQUEST)
        else:
            return Response({'message': 'Something is wrong with token'}, status=HTTP_400_BAD_REQUEST)


class CompletedChatOpinionCase(APIView):

    permission_classes = [IsAuthenticated]

    def get_object(self, pk):
        try:
            return booking.objects.get(pk=pk)
        except booking.DoesNotExist:
            raise Http404

    def post(self, request, pk, format=None):
        booking = self.get_object(pk=pk)
        if self.request.user.is_authenticated and self.request.user.is_doctor:
            doctor = self.request.user.doctor
            if booking.doctor == doctor:
                booking.status = COMPLETE
                booking.save()
                serializer = ChatOpinionSerializer(
                    booking, user=request.user)
                return Response(serializer.data)
            else:
                return Response({'message': 'You are not authorized for complete this booking'}, status=HTTP_400_BAD_REQUEST)
        else:
            return Response({'message': 'Something is wrong with token'}, status=HTTP_400_BAD_REQUEST)
