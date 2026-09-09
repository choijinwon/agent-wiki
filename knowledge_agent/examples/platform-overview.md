# Layered Kubernetes Platform

이 플랫폼은 g0부터 g6까지 순차적인 레이어로 구성됩니다. g0는 공통 네임스페이스를 만들고, g1은 Argo CD, g2는 Argo Workflows, g3는 rootless BuildKit을 설치합니다. g4와 g5는 KServe CRD 및 컨트롤러를 구성하고 g6는 ServingRuntime을 준비합니다.

모델 이미지는 Ubuntu, CUDA, Python, PyTorch, MLflow, KServe, non-root identity 순서로 빌드합니다. 로컬 이미지는 Harbor에 저장하고 Argo Workflows가 빌드를 실행합니다. Git에 반영된 Helm values 변경은 Argo CD가 감지해 모델을 배포합니다.

장애가 발생하면 먼저 현재 Kubernetes context와 각 namespace의 pod 상태를 확인합니다. BuildKit 빌드 장애는 buildkit namespace의 daemon 로그를, 모델 serving 장애는 model-serving namespace의 InferenceService 상태를 확인합니다. 운영 환경에서는 BuildKit TCP endpoint에 mTLS 또는 네트워크 정책을 적용해야 합니다.
