from django.contrib import admin

from .models import (
    ChatOpinionQuestion, ChatOptionAnswer,
    ChatOpinionConversation
)

# Register your models here.
admin.site.register(ChatOpinionQuestion)
admin.site.register(ChatOptionAnswer)
admin.site.register(ChatOpinionConversation)
