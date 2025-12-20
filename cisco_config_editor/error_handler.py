# cisco_config_manager/error_handler.py
import sys
import traceback
from PySide6.QtWidgets import QMessageBox, QApplication
from PySide6.QtCore import QObject, Signal, QCoreApplication


class ErrorHandler(QObject):
    """실제로 창을 띄우는 에러 핸들러"""

    # 시그널 정의 - 메인 스레드에서 실행되도록
    show_error_signal = Signal(str, str)

    def __init__(self):
        super().__init__()
        self.show_error_signal.connect(self._show_error_dialog)
        self.setup_global_handler()

    def setup_global_handler(self):
        """전역 예외 처리 설정"""
        sys.excepthook = self.handle_exception

    def handle_exception(self, exc_type, exc_value, exc_traceback):
        """모든 예외 처리 - 실제로 창을 띄움"""
        if exc_type == KeyboardInterrupt:
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return

        error_msg = str(exc_value)
        error_type = exc_type.__name__
        error_details = ''.join(traceback.format_exception(exc_type, exc_value, exc_traceback))

        print("\n" + "=" * 60)
        print(f"🚨 치명적 오류 발생: {error_type}")
        print(f"메시지: {error_msg}")
        print("=" * 60)

        self.save_error_log(error_type, error_msg, error_details)

        app = QCoreApplication.instance()
        if app:
            self.show_error_signal.emit(
                f"애플리케이션 오류 ({error_type})",
                f"다음 오류가 발생했습니다:\n\n"
                f"📛 {error_msg}\n\n"
                f"자세한 내용은 로그 파일을 확인하세요."
            )

    def save_error_log(self, error_type, error_msg, error_details):
        try:
            from datetime import datetime
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            with open('error_log.txt', 'a', encoding='utf-8') as f:
                f.write(f"\n{'=' * 60}\n")
                f.write(f"[{timestamp}] {error_type}\n")
                f.write(f"메시지: {error_msg}\n")
                f.write(f"{'=' * 60}\n")
                f.write(error_details)
                f.write("\n")
            print(f"📝 에러 로그 저장됨: error_log.txt")
        except Exception as e:
            print(f"❌ 로그 저장 실패: {e}")

    def _show_error_dialog(self, title, message):
        """실제로 에러 다이얼로그 표시 (메인 스레드에서 실행)"""
        try:
            app = QApplication.instance()
            if not app: return

            # [수정] 부모 창 찾기 로직 개선 (QWindow 대신 QWidget 찾기)
            parent = app.activeWindow()
            if not parent:
                # 활성화된 창이 없으면 최상위 위젯 중 보이는 첫 번째를 선택
                widgets = app.topLevelWidgets()
                for w in widgets:
                    if w.isVisible():
                        parent = w
                        break

            # parent가 여전히 None이어도 QMessageBox는 정상 동작함 (화면 중앙에 뜸)
            msg_box = QMessageBox(parent)
            msg_box.setIcon(QMessageBox.Critical)
            msg_box.setWindowTitle(title)
            msg_box.setText(message)
            msg_box.setStandardButtons(QMessageBox.Ok)

            detail_btn = msg_box.addButton("📋 상세 정보", QMessageBox.ActionRole)
            detail_btn.clicked.connect(lambda: self._show_details_dialog(parent))

            msg_box.exec()

        except Exception as e:
            # 에러 핸들러 자체 에러는 콘솔에만 출력
            print(f"❌ 에러 다이얼로그 생성 실패: {e}")

    def _show_details_dialog(self, parent):
        try:
            with open('error_log.txt', 'r', encoding='utf-8') as f:
                logs = f.read()

            # 마지막 로그 블록 추출
            error_blocks = logs.split('=' * 60)
            last_error = "로그를 불러올 수 없습니다."
            if len(error_blocks) >= 3:
                last_error = error_blocks[-2] + '\n' + error_blocks[-1]

            dialog = QMessageBox(parent)
            dialog.setWindowTitle("오류 상세 정보")
            dialog.setIcon(QMessageBox.Information)
            dialog.setText("최근 발생한 오류 로그:")
            dialog.setDetailedText(last_error.strip())
            dialog.setStandardButtons(QMessageBox.Close)
            dialog.exec()
        except:
            pass


error_handler = ErrorHandler()