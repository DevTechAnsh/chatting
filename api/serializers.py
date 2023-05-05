from collections import OrderedDict
from core.choices import PATIENT
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers
from wagtail.core.models import Collection
from wagtail.documents.models import get_document_model
from patient.api.serializers import PatientSerializer
from utils.file_upload import filename_to_title
from django.utils import timezone
from datetime import datetime
from ..models import Complaint, ChatOptionAnswer, ChatOpinionConversation
from booking.models import booking
from django.utils import timezone
from datetime import datetime


STATUSES = {
    'new': _('New'),
    'in-progress': _('In Progress'),
    'reply': _('Reply'),
    'closed': _('Closed')
}


class ComplaintSerializer(serializers.ModelSerializer):
    class Meta:
        model = Complaint
        exclude = ('created', 'modified')

    def validate(self, attrs):
        booking = attrs.get('booking', None)
        request = self.context['request']
        user = request.user
        attrs['user'] = user
        attrs['type'] = PATIENT
        errors = OrderedDict()
        if booking:
            if not booking.user == user:
                errors['booking'] = [_("Invalid booking id")]

        if errors:
            raise serializers.ValidationError(errors)
        return attrs


class ChatOptionAnswerSerializers(serializers.ModelSerializer):
    question_label = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = ChatOptionAnswer
        fields = ('question_label', 'answer')

    def get_question_label(self, obj):
        return obj.question.label if obj.question else obj.question_label


class ConversationSerializer(serializers.ModelSerializer):
    booking_data = serializers.SerializerMethodField(read_only=True)
    patient_can_replay = serializers.ReadOnlyField()
    doctor_attachments = serializers.SerializerMethodField(read_only=True)
    patient_attachments = serializers.SerializerMethodField(read_only=True)
    files = serializers.ListField(required=False, write_only=True)

    class Meta:
        model = ChatOpinionConversation
        exclude = ('modified',)

        extra_kwargs = {
            'patient': {
                'error_messages': {
                    'required': _('Please select patient Profile')
                }
            }
        }

    def __init__(self, *args, **kwargs):
        super(ConversationSerializer, self).__init__(*args, **kwargs)
        self.fields['patient'].required = True
        self.fields['doctor'].required = True

    def get_booking_data(self, obj):
        request = self.context['request']
        from booking.api.serializers import bookingSerializer
        return bookingSerializer(instance=obj.booking,
                                     context={'request': request}).data

    def get_patient_attachments(self, obj):
        request = self.context['request']
        from booking.api.serializers import AttachmentSerializer
        qs = obj.patient_attachments.all()
        if qs.exists():
            return AttachmentSerializer(qs, many=True,
                                        context={'request': request}
                                        ).data
        return []

    def get_doctor_attachments(self, obj):
        request = self.context['request']
        from booking.api.serializers import AttachmentSerializer
        qs = obj.doctor_attachments.all()
        if qs.exists():
            return AttachmentSerializer(qs, many=True,
                                        context={'request': request}
                                        ).data
        return []

    def create(self, validated_data):
        booking = validated_data.get('booking')
        messages = ChatOpinionConversation.objects.filter(
            booking=booking,
            is_doctor_message=False
        )
        doctor_message = ChatOpinionConversation.objects.filter(
            booking=booking,
            is_doctor_message=True
        )
        if self.context.get('request', None):
            user = self.context.get('request').user
        if not messages.count() < 3 and not user.is_doctor:
            raise serializers.ValidationError({
                'message': [_('Maximum Replies limit is 3')]
            })

        files = validated_data.pop('files', None)
        if user.is_doctor and user.doctor == booking.doctor:
            validated_data['is_doctor_message'] = True
        instance = super(ConversationSerializer, self).create(validated_data)
        if files:
            self.save_files(files, instance)
        return instance

    def save_files(self, files, instance):
        from common.api.serializer import CustomBase64FileField

        request = self.context['request']
        DocumentModel = get_document_model()

        if request.user.is_authenticated:
            user_slug = request.user.slug
        else:
            user_slug = "guest"

        try:
            collection = Collection.objects.get(name=user_slug)
        except:
            collection = Collection(name=user_slug)
            root_collection = Collection.get_first_root_node()
            root_collection.add_child(instance=collection)

        for f in files:
            for key, value in f.items():
                data = CustomBase64FileField(value, file_name=key)
                _file = data.to_internal_value(value)

                name = _file.name
                if _file:
                    file = DocumentModel(
                        file=_file,
                        title=filename_to_title(name),
                        collection=collection
                    )
                    file.save()
                    if instance.is_doctor_message:
                        instance.doctor_attachments.add(file)
                    else:
                        instance.patient_attachments.add(file)


class ChatOpinionSerializer(serializers.ModelSerializer):
    status = serializers.SerializerMethodField(read_only=True)
    status_display = serializers.SerializerMethodField(read_only=True)
    patient = serializers.SerializerMethodField(read_only=True)
    doctor = serializers.SerializerMethodField(read_only=True)
    creation_time = serializers.SerializerMethodField(read_only=True)
    creation_date = serializers.SerializerMethodField(read_only=True)
    can_share_data = serializers.SerializerMethodField(read_only=True)
    questions_ans = ChatOptionAnswerSerializers(
        required=False, many=True, source='booking_Chat_opinion_answer'
    )
    attachments = serializers.SerializerMethodField(read_only=True)

    def __init__(self, *args, **kwargs):
        remove_fields = kwargs.pop('remove_fields', None)
        self.user = kwargs.pop('user', None)
        super(ChatOpinionSerializer, self).__init__(*args, **kwargs)

        if remove_fields:
            for field_name in remove_fields:
                self.fields.pop(field_name)

    class Meta:
        model = booking
        fields = ('id', 'status', 'status_display', 'patient', 'doctor', 'creation_time',
                  'creation_date', 'attachments', 'questions_ans', 'can_share_data')

    def get_attachments(self, obj):
        from booking.api.serializers import AttachmentSerializer
        return AttachmentSerializer(obj.attachments, many=True).data

    def get_doctor(self, obj):
        from doctor.api.serializers import DoctorSerializer
        return DoctorSerializer(obj.doctor, read_only=True, remove_fields=['hospital']).data

    def get_can_share_data(self, obj):
        if obj.can_share_data:
            return obj.can_share_data
        return False

    def get_status(self, obj):
        if obj.status:
            return obj.status
        return None

    def get_status_display(self, obj):
        if obj.status == 'completed' or obj.status == 'cancelled':
            return STATUSES.get('closed')
        if self.context.get('request', None):
            if self.context['request'].GET.get('status', None) == 'reply' and obj.status == 'in-progress':
                return STATUSES.get('reply')
            else:
                return STATUSES.get(obj.status)
        else:
            return STATUSES.get(obj.status)

    def get_patient(self, obj):
        if obj.can_share_data:
            serializer = PatientSerializer(obj.patient, read_only=True)
        else:
            serializer = PatientSerializer(
                obj.patient, read_only=True, remove_fields=["medical_details"])
        return serializer.data

    def get_creation_time(self, obj):
        creation_time = timezone.localtime(obj.created)
        return creation_time.strftime('%I:%M %p')

    def get_creation_date(self, obj):
        UTC_OFFSET_TIMEDELTA = datetime.now() - datetime.utcnow()
        correct_date = obj.created + UTC_OFFSET_TIMEDELTA
        return correct_date.strftime('%b %d, %Y')
