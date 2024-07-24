
import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.view.MotionEvent
import android.view.View
import android.view.WindowManager
import android.widget.Toast

class DrawOverlay(context: Context) : View(context) {
    private val paint = Paint()
    private var squareSize = 200f // Size of the square (about the size of a thumb)
    private var left = 0f
    private var top = 0f
    private var right = 0f
    private var bottom = 0f

    init {
        paint.color = Color.BLACK
        paint.style = Paint.Style.FILL
        updateBoxCoordinates()
    }

    private fun updateBoxCoordinates() {
        left = (width - squareSize) / 2
        top = (height - squareSize) / 2
        right = left + squareSize
        bottom = top + squareSize
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        canvas.drawRect(left, top, right, bottom, paint)
    }

    override fun onTouchEvent(event: MotionEvent): Boolean {
        if (event.action == MotionEvent.ACTION_DOWN) {
            Toast.makeText(context, "Overlay clicked!", Toast.LENGTH_SHORT).show()
            moveBoxTo((Math.random() * width).toFloat(), (Math.random() * height).toFloat())
            return true
        }
        return super.onTouchEvent(event)
    }

    fun moveBoxTo(x: Float, y: Float) {
        left = (x - squareSize / 2).toFloat()
        top = (y - squareSize / 2).toFloat()
        right = left + squareSize
        bottom = top + squareSize
        invalidate() // Redraw the view
    }

    fun resizeBox(newSize: Float) {
        squareSize = newSize
        updateBoxCoordinates()
        invalidate() // Redraw the view
    }
}

class OverlayManager(private val context: Context) {
    private var overlayView: DrawOverlay? = null

    fun showOverlay() {
        if (overlayView == null) {
            overlayView = DrawOverlay(context)
            val params = WindowManager.LayoutParams(
                WindowManager.LayoutParams.WRAP_CONTENT,
                WindowManager.LayoutParams.WRAP_CONTENT,
                WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE,
                WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE
            ).apply {
                width = 400 // Set the width of the overlay
                height = 400 // Set the height of the overlay
            }
            val windowManager = context.getSystemService(Context.WINDOW_SERVICE) as WindowManager
            windowManager.addView(overlayView, params)
        }
    }

    fun removeOverlay() {
        overlayView?.let {
            val windowManager = context.getSystemService(Context.WINDOW_SERVICE) as WindowManager
            windowManager.removeView(it)
            overlayView = null
        }
    }

    fun moveOverlayBoxTo(x: Float, y: Float) {
        overlayView?.moveBoxTo(x, y)
    }

    fun resizeOverlayBox(newSize: Float) {
        overlayView?.resizeBox(newSize)
    }
}