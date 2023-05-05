from auditlog.registry import auditlog
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import models
from django.dispatch import receiver
from django.utils.translation import gettext_lazy as _, activate, get_language
from django_extensions.db.models import TimeStampedModel
from wagtail.admin.edit_handlers import FieldPanel
from wagtail.contrib.forms.models import AbstractFormField
from wagtail.documents.models import get_document_model

from core.choices import COMPLAINT_FROM, PATIENT
from notification.models import Notification


User = get_user_model()
Document = get_document_model()


class ChatOpinionQuestion(AbstractFormField):

    code = models.CharField(_('Field Code'), max_length=100, unique=True)

    panels = AbstractFormField.panels + [FieldPanel('code')]

    class Meta:
        verbose_name = _('Chat Opinion Question')
        verbose_name_plural = _('Chat Opinion Questions')

    def __str__(self):
        return self.label

    @property
    def clean_name(self):
        return str(self.code)


class ChatOptionAnswer(models.Model):

    # Target
    question = models.ForeignKey(ChatOpinionQuestion,
                                 related_name='question',
                                 on_delete=models.SET_NULL, null=True)
    question_label = models.TextField(_('Question Text'), null=True,
                                      blank=True)
    # source table
    booking = models.ForeignKey('booking.booking',
                                    related_name='booking_Chat_opinion_answer',
                                    on_delete=models.SET_NULL, null=True)

    basket = models.ForeignKey('booking.Basket',
                               related_name='basket_Chat_opinion_answer',
                               on_delete=models.SET_NULL, null=True)

    answer = models.TextField(_('Answer'), null=True, blank=True)


class ChatOpinionConversation(TimeStampedModel):

    patient = models.ForeignKey('patient.Patient',
                                related_name='conversation_patient',
                                null=True, blank=True,
                                on_delete=models.CASCADE)
    doctor = models.ForeignKey('doctor.Doctor',
                               related_name='conversation_doctor',
                               null=True, blank=True,
                               on_delete=models.SET_NULL)

    doctor_attachments = models.ManyToManyField(Document, blank=True,
                                                related_name='conversation_doctor_attachments')

    patient_attachments = models.ManyToManyField(Document, blank=True,
                                                 related_name='conversation_patient_attachments')

    is_doctor_message = models.BooleanField(_('Is message Sent from Doctor'),
                                            default=False)

    booking = models.ForeignKey('booking.booking',
                                    related_name='booking_conversation',
                                    null=False, blank=False,
                                    on_delete=models.CASCADE)
    message = models.TextField(_('Conversation Message'), default='')
    notification = models.ForeignKey('notification.Notification', blank=True, null=True,
                                     related_name='conversation_notification', on_delete=models.SET_NULL)

    class Meta:
        verbose_name = _('Conversation')
        verbose_name_plural = _('Conversations')
        ordering = ['-created']

    def __str__(self):
        try:
            return f"{self.patient.get_full_name()} and " \
                   f"{self.doctor.user.get_full_name()}"
        except:
            return self.message

    @property
    def patient_can_replay(self):
        messages = ChatOpinionConversation.objects.filter(
            patient=self.patient,
            booking=self.booking,
            is_doctor_message=False
        )
        if messages.count() < 3:
            return True
        return False

    @property
    def reply_left(self):
        replies = settings.PATIENT_REPLY_LIMIT + \
            1 if self.is_doctor_message else settings.PATIENT_REPLY_LIMIT
        messages = ChatOpinionConversation.objects.filter(
            patient=self.patient,
            booking=self.booking,
            is_doctor_message=self.is_doctor_message,
            created__lte=self.created
        )
        return replies - messages.count()


class Complaint(TimeStampedModel):
    type = models.CharField(verbose_name=_('Complaint From'),
                            choices=COMPLAINT_FROM, default=PATIENT,
                            max_length=20)
    description = models.TextField(_('Description of the complaint'),
                                   null=False, blank=False)
    booking = models.ForeignKey('booking.booking',
                                    related_name='booking_complaint',
                                    on_delete=models.CASCADE)
    user = models.ForeignKey(User, verbose_name=_('Complaint From User'),
                             related_name='complaint_from',
                             null=True, blank=True,
                             on_delete=models.SET_NULL)

    class Meta:
        verbose_name = _('Complaint')
        verbose_name_plural = _('Complaints')

    def __str__(self):
        return f"{self.booking.patient.get_full_name() if self.booking.patient else None} against " \
               f"{self.booking.doctor.user.get_full_name()}"


auditlog.register(ChatOpinionQuestion)
auditlog.register(ChatOptionAnswer)
auditlog.register(ChatOpinionConversation)
auditlog.register(Complaint)
