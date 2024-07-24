package red.steele.injest

import android.accessibilityservice.AccessibilityService
import android.util.Log
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo

class ScreenService : AccessibilityService() {

    private var mDebugDepth = 0

    override fun onAccessibilityEvent(event: AccessibilityEvent) {
        Log.v(TAG, String.format(
            "onAccessibilityEvent: type = [ %s ], class = [ %s ], package = [ %s ], time = [ %s ], text = [ %s ]",
            getEventType(event), event.className, event.packageName,
            event.eventTime, getEventText(event)))

        mDebugDepth = 0
        val mNodeInfo = event.source
        printAllViews(mNodeInfo)
    }

    override fun onInterrupt() {
        // Handle interrupt
    }

    private fun printAllViews(mNodeInfo: AccessibilityNodeInfo?) {
        if (mNodeInfo == null) return
        var log = ""
        for (i in 0 until mDebugDepth) {
            log += "."
        }
        log += "(${mNodeInfo.text} <-- ${mNodeInfo.viewIdResourceName})"
        Log.d(TAG, log)
        if (mNodeInfo.childCount < 1) return
        mDebugDepth++

        for (i in 0 until mNodeInfo.childCount) {
            printAllViews(mNodeInfo.getChild(i))
        }
        mDebugDepth--
    }

    private fun getEventType(event: AccessibilityEvent): String {
        return when (event.eventType) {
            AccessibilityEvent.TYPE_VIEW_CLICKED -> "TYPE_VIEW_CLICKED"
            AccessibilityEvent.TYPE_VIEW_FOCUSED -> "TYPE_VIEW_FOCUSED"
            else -> "OTHER"
        }
    }

    private fun getEventText(event: AccessibilityEvent): String {
        val sb = StringBuilder()
        for (s in event.text) {
            sb.append(s)
        }
        return sb.toString()
    }

    private fun extractTextFromNode(node: AccessibilityNodeInfo?): String {
        if (node == null) return ""
        val sb = StringBuilder()
        if (!node.text.isNullOrEmpty()) {
            sb.append(node.text).append("\n")
        }
        for (i in 0 until node.childCount) {
            sb.append(extractTextFromNode(node.getChild(i)))
        }
        return sb.toString()
    }

    companion object {
        private const val TAG = "MyAccessibilityService"
    }
}