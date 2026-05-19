import time
import logging

class RequestTimingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.logger = logging.getLogger(__name__)

    def __call__(self, request):

        before_time = time.time()
        response = self.get_response(request)  
        after_time = time.time()

        self.logger.info(f"[{request.method}] {request.path} —  {(after_time-before_time)* 1000}")
        return response