from rest_framework import serializers
from .models import JobPosting

class JobPostingSerializer(serializers.ModelSerializer):
    """
    JobPosting용 DRF Serializer.

    - fields='__all__' 이므로 모델에 존재하는 모든 필드가 노출됩니다.
      (여기에는 새로 추가된 is_active(BooleanField), first_seen_at(DateTimeField)도 포함)
    - first_seen_at은 auto_now_add=True(서버가 최초 생성 시각을 지정) 이므로
      클라이언트가 수정할 수 없도록 read_only로 둡니다.
    """
    class Meta:
        model = JobPosting
        fields = '__all__'
        read_only_fields = ('first_seen_at',)
