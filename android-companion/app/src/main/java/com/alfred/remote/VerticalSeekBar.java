package com.alfred.remote;

import android.content.Context;
import android.graphics.Canvas;
import android.util.AttributeSet;
import android.view.MotionEvent;
import android.widget.SeekBar;

/** Compact native vertical slider used to position the TV dashboard. */
public class VerticalSeekBar extends SeekBar {
    public VerticalSeekBar(Context context) { super(context); }
    public VerticalSeekBar(Context context, AttributeSet attrs) { super(context, attrs); }
    public VerticalSeekBar(Context context, AttributeSet attrs, int style) { super(context, attrs, style); }

    @Override
    protected synchronized void onMeasure(int widthMeasureSpec, int heightMeasureSpec) {
        super.onMeasure(heightMeasureSpec, widthMeasureSpec);
        setMeasuredDimension(getMeasuredHeight(), getMeasuredWidth());
    }

    @Override
    protected void onDraw(Canvas canvas) {
        canvas.rotate(-90);
        canvas.translate(-getHeight(), 0);
        super.onDraw(canvas);
    }

    @Override
    public boolean onTouchEvent(MotionEvent event) {
        if (!isEnabled()) return false;
        event.setLocation(getHeight() - event.getY(), getWidth() / 2f);
        return super.onTouchEvent(event);
    }

    @Override
    public boolean performClick() {
        super.performClick();
        return true;
    }
}
