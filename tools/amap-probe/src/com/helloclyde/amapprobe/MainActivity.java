package com.helloclyde.amapprobe;

import android.app.Activity;
import android.os.Bundle;
import android.text.InputType;
import android.widget.*;
import com.amap.api.maps.MapsInitializer;
import com.amap.api.navi.*;
import com.amap.api.navi.model.*;
import org.json.*;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.*;

/** Isolated diagnostic application; never ships in the media center. */
public class MainActivity extends Activity {
    private TextView status;
    private AMapNavi navi;
    private Button calculate;
    private final SimpleNaviListener listener = new SimpleNaviListener() {
        @Override public void onInitNaviSuccess() { runOnUiThread(() -> { status.setText("SDK 初始化成功，正在算路"); route(); }); }
        @Override public void onInitNaviFailure() { show("SDK 初始化失败：请检查 Android Key、包名和签名绑定"); }
        @Override public void onCalculateRouteFailure(int code) { show("算路失败，错误码：" + code); }
        @Override public void onCalculateRouteSuccess(int[] ids) { saveRoutes(); }
    };
    @Override public void onCreate(Bundle saved) {
        super.onCreate(saved);
        LinearLayout box = new LinearLayout(this); box.setOrientation(LinearLayout.VERTICAL); box.setPadding(24,32,24,24);
        TextView description = new TextView(this);
        description.setText("高德 SDK 协议测试\n仅测试固定的北京站→故宫路线，不请求手机定位。\n点击下方按钮表示同意初始化高德 SDK 并向其发送测试请求及 SDK 必要设备信息。\nKey 仅在当前进程使用，不写入日志或文件。"); box.addView(description);
        EditText key = new EditText(this); key.setHint("输入绑定此应用的高德 Android Key"); key.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD); key.setSaveEnabled(false); box.addView(key);
        calculate = new Button(this); calculate.setText("同意并开始固定路线测试"); box.addView(calculate);
        status = new TextView(this); status.setTextIsSelectable(true); box.addView(status); setContentView(box);
        try { System.loadLibrary("c++_shared"); System.loadLibrary("AMapSDK_NAVI_v11_3_100"); status.setText("ARM 导航原生库加载成功；等待 Android Key"); }
        catch (Throwable error) { status.setText("原生库加载失败：" + error.getClass().getSimpleName() + ": " + error.getMessage()); }
        calculate.setOnClickListener(v -> {
            String value = key.getText().toString().trim();
            if (value.isEmpty()) { status.setText("请先填写 Android Key"); return; }
            calculate.setEnabled(false);
            try {
                if (navi == null) {
                    MapsInitializer.updatePrivacyShow(this, true, true);
                    MapsInitializer.updatePrivacyAgree(this, true);
                    AMapNavi.setApiKey(this, value);
                    navi = AMapNavi.getInstance(this);
                    navi.addAMapNaviListener(listener);
                    status.setText("等待 SDK 初始化…");
                } else route();
            } catch (Throwable error) { show("初始化异常：" + error.getClass().getSimpleName()); }
        });
    }
    private void show(String text) { runOnUiThread(() -> { status.setText(text); calculate.setEnabled(true); }); }
    private void route() {
        List<NaviLatLng> start = Collections.singletonList(new NaviLatLng(39.90403,116.427281));
        List<NaviLatLng> end = Collections.singletonList(new NaviLatLng(39.917337,116.397056));
        if (!navi.calculateDriveRoute(start, end, Collections.emptyList(), 10)) show("算路请求未被接受");
    }
    private void saveRoutes() {
        try {
            JSONArray routes = new JSONArray();
            for (Map.Entry<Integer,AMapNaviPath> entry : navi.getNaviPaths().entrySet()) {
                AMapNaviPath path=entry.getValue(); JSONObject row=new JSONObject();
                row.put("id",entry.getKey()); row.put("distance",path.getAllLength()); row.put("seconds",path.getAllTime());
                row.put("toll",path.getTollCost()); row.put("trafficLights",path.getTrafficLightCount());
                JSONArray coords=new JSONArray();
                for (NaviLatLng point:path.getCoordList()) coords.put(new JSONArray().put(point.getLongitude()).put(point.getLatitude()));
                row.put("coordinates",coords);routes.put(row);
            }
            try(FileOutputStream out=openFileOutput("routes.json",MODE_PRIVATE)) { out.write(routes.toString(2).getBytes(StandardCharsets.UTF_8)); }
            show("算路成功：" + routes.length() + " 条路线；已保存到应用私有文件 routes.json");
        } catch(Exception error) { show("结果导出失败：" + error.getClass().getSimpleName()); }
    }
    @Override public void onDestroy() {
        if (navi != null) { navi.removeAMapNaviListener(listener); AMapNavi.destroy(); }
        super.onDestroy();
    }
}
