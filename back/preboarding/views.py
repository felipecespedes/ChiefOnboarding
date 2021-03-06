from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Preboarding
from .serializers import PreboardingSerializer


class PreboardingViewSet(viewsets.ModelViewSet):
    serializer_class = PreboardingSerializer
    queryset = Preboarding.templates.all().order_by('id')

    @action(detail=True, methods=['post'])
    def duplicate(self, request, pk):
        self.get_object().duplicate()
        return Response()
