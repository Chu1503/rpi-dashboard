package com.alfred.remote;

import android.Manifest;
import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.os.Bundle;
import android.speech.RecognitionListener;
import android.speech.RecognizerIntent;
import android.speech.SpeechRecognizer;
import android.view.View;
import android.view.inputmethod.EditorInfo;
import android.widget.EditText;
import android.widget.ImageButton;
import android.widget.LinearLayout;
import android.widget.SeekBar;
import android.widget.TextView;

import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.Inet4Address;
import java.net.InetAddress;
import java.net.NetworkInterface;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Enumeration;
import java.util.LinkedHashSet;
import java.util.Locale;
import java.util.Set;
import java.util.concurrent.CompletionService;
import java.util.concurrent.ExecutorCompletionService;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class MainActivity extends Activity implements RecognitionListener {
    private static final int AUDIO_PERMISSION_REQUEST = 41;
    private static final String DEFAULT_SERVER = "http://192.168.1.41:8080";
    private static final String LEGACY_SERVER = "http://alfred.local:8080";
    private static final String PREFS = "alfred_remote";
    private static final String SERVER_KEY = "server_url";
    private static final String TOKEN_KEY = "remote_token";

    private final ExecutorService network = Executors.newSingleThreadExecutor();
    private SharedPreferences preferences;
    private TextView connectionStatus;
    private TextView answerText;
    private TextView errorText;
    private EditText queryInput;
    private ImageButton powerButton;
    private ImageButton refreshButton;
    private ImageButton sendButton;
    private ImageButton micButton;
    private VerticalSeekBar scrollControl;
    private View[] tvControls;
    private SpeechRecognizer speechRecognizer;
    private Intent speechIntent;
    private boolean listening;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        preferences = getSharedPreferences(PREFS, MODE_PRIVATE);
        migrateLegacyAddress();
        connectionStatus = findViewById(R.id.connectionStatus);
        answerText = findViewById(R.id.answerText);
        errorText = findViewById(R.id.errorText);
        queryInput = findViewById(R.id.queryInput);
        powerButton = findViewById(R.id.powerButton);
        refreshButton = findViewById(R.id.refreshButton);
        sendButton = findViewById(R.id.sendButton);
        micButton = findViewById(R.id.micButton);
        scrollControl = findViewById(R.id.scrollControl);
        tvControls = new View[]{findViewById(R.id.volumeUpButton), findViewById(R.id.volumeDownButton),
                findViewById(R.id.hdmi1Button), findViewById(R.id.hdmi2Button)};
        String[] tvActions = {"volume_up", "volume_down", "hdmi_1", "hdmi_2"};
        for (int i = 0; i < tvControls.length; i++) {
            final String action = tvActions[i];
            tvControls[i].setOnClickListener(view -> sendTvCommand(action));
        }

        findViewById(R.id.alfredTitle).setOnLongClickListener(view -> {
            showSettings();
            return true;
        });
        powerButton.setOnClickListener(view -> sendPower());
        refreshButton.setOnClickListener(view -> refreshDashboardScreen());
        sendButton.setOnClickListener(view -> askAlfred(queryInput.getText().toString()));
        micButton.setOnClickListener(view -> toggleListening());
        scrollControl.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener() {
            @Override public void onProgressChanged(SeekBar seekBar, int progress, boolean fromUser) { }
            @Override public void onStartTrackingTouch(SeekBar seekBar) { }
            @Override public void onStopTrackingTouch(SeekBar seekBar) {
                scrollDashboard(seekBar.getProgress() / 100.0);
            }
        });
        queryInput.setOnEditorActionListener((view, actionId, event) -> {
            if (actionId == EditorInfo.IME_ACTION_SEND) {
                askAlfred(queryInput.getText().toString());
                return true;
            }
            return false;
        });

        prepareSpeechRecognizer();
        checkServer();
        if (token().isEmpty()) showSettings();
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (preferences != null) checkServer();
    }

    @Override
    protected void onDestroy() {
        if (speechRecognizer != null) speechRecognizer.destroy();
        network.shutdownNow();
        super.onDestroy();
    }

    private void migrateLegacyAddress() {
        if (LEGACY_SERVER.equals(preferences.getString(SERVER_KEY, ""))) {
            preferences.edit().putString(SERVER_KEY, DEFAULT_SERVER).apply();
        }
    }

    private void prepareSpeechRecognizer() {
        if (!SpeechRecognizer.isRecognitionAvailable(this)) {
            micButton.setEnabled(false);
            showError("Speech recognition is unavailable on this phone.");
            return;
        }
        speechRecognizer = SpeechRecognizer.createSpeechRecognizer(this);
        speechRecognizer.setRecognitionListener(this);
        speechIntent = new Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH);
        speechIntent.putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM);
        speechIntent.putExtra(RecognizerIntent.EXTRA_LANGUAGE, Locale.US.toLanguageTag());
        speechIntent.putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 1);
        speechIntent.putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true);
    }

    private void toggleListening() {
        if (listening) {
            speechRecognizer.stopListening();
            return;
        }
        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.RECORD_AUDIO}, AUDIO_PERMISSION_REQUEST);
            return;
        }
        startListening();
    }

    private void startListening() {
        if (speechRecognizer == null) {
            showError("Speech recognition is unavailable on this phone.");
            return;
        }
        clearError();
        queryInput.setText("");
        setListening(true);
        speechRecognizer.startListening(speechIntent);
    }

    private void setListening(boolean active) {
        listening = active;
        micButton.setSelected(active);
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (requestCode != AUDIO_PERMISSION_REQUEST) return;
        if (grantResults.length > 0 && grantResults[0] == PackageManager.PERMISSION_GRANTED) {
            startListening();
        } else {
            showError("Microphone permission is required.");
        }
    }

    @Override public void onReadyForSpeech(Bundle params) { setListening(true); }
    @Override public void onBeginningOfSpeech() { }
    @Override public void onRmsChanged(float rmsdB) { }
    @Override public void onBufferReceived(byte[] buffer) { }
    @Override public void onEndOfSpeech() { }

    @Override
    public void onError(int error) {
        setListening(false);
        String message;
        switch (error) {
            case SpeechRecognizer.ERROR_AUDIO: message = "Microphone audio failed."; break;
            case SpeechRecognizer.ERROR_INSUFFICIENT_PERMISSIONS: message = "Microphone permission is required."; break;
            case SpeechRecognizer.ERROR_NETWORK:
            case SpeechRecognizer.ERROR_NETWORK_TIMEOUT: message = "Speech service network error."; break;
            case SpeechRecognizer.ERROR_NO_MATCH: message = "I could not understand that."; break;
            case SpeechRecognizer.ERROR_RECOGNIZER_BUSY: message = "Speech recognizer is busy. Try again."; break;
            case SpeechRecognizer.ERROR_SPEECH_TIMEOUT: message = "No speech was detected."; break;
            default: message = "Speech recognition failed."; break;
        }
        showError(message);
    }

    @Override
    public void onResults(Bundle results) {
        setListening(false);
        ArrayList<String> matches = results.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION);
        if (matches == null || matches.isEmpty()) {
            showError("I could not understand that.");
            return;
        }
        String transcript = matches.get(0);
        answerText.setText(transcript);
        askAlfred(transcript);
    }

    @Override
    public void onPartialResults(Bundle partialResults) {
        ArrayList<String> matches = partialResults.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION);
        if (matches != null && !matches.isEmpty()) answerText.setText(matches.get(0));
    }

    @Override public void onEvent(int eventType, Bundle params) { }

    private void setBusy(boolean busy) {
        for (View control : tvControls) control.setEnabled(!busy);
        powerButton.setEnabled(!busy);
        refreshButton.setEnabled(!busy);
        sendButton.setEnabled(!busy);
        micButton.setEnabled(!busy && speechRecognizer != null);
        scrollControl.setEnabled(!busy);
    }

    private void checkServer() {
        network.execute(() -> {
            try {
                JSONObject result = request("GET", "/api/tv/status", null, false);
                boolean available = result.optBoolean("available", false);
                runOnUiThread(() -> {
                    connectionStatus.setText("Connected");
                    connectionStatus.setTextColor(Color.parseColor("#247B49"));
                    powerButton.setEnabled(available);
                    for (View control : tvControls) control.setEnabled(available);
                    refreshButton.setEnabled(true);
                    scrollControl.setEnabled(true);
                });
            } catch (Exception error) {
                runOnUiThread(() -> {
                    connectionStatus.setText("Not connected");
                    connectionStatus.setTextColor(Color.parseColor("#A32130"));
                    powerButton.setEnabled(false);
                    for (View control : tvControls) control.setEnabled(false);
                    refreshButton.setEnabled(false);
                    scrollControl.setEnabled(false);
                });
            }
        });
    }

    private void sendPower() {
        if (!ensureConfigured()) return;
        clearError();
        answerText.setText("");
        setBusy(true);
        network.execute(() -> {
            try {
                JSONObject result = request("POST", "/api/tv/power", new JSONObject().put("action", "power"), true);
                runOnUiThread(() -> {
                    setBusy(false);
                });
            } catch (Exception error) {
                showRequestError(error);
            }
        });
    }

    private void sendTvCommand(String action) {
        if (!ensureConfigured()) return;
        clearError();
        setBusy(true);
        network.execute(() -> {
            try {
                request("POST", "/api/tv/command", new JSONObject().put("action", action), true);
                runOnUiThread(() -> setBusy(false));
            } catch (Exception error) {
                showRequestError(error);
            }
        });
    }

    private void refreshDashboardScreen() {
        if (!ensureConfigured()) return;
        clearError();
        setBusy(true);
        network.execute(() -> {
            try {
                request("POST", "/api/display/refresh", new JSONObject(), true);
                runOnUiThread(() -> setBusy(false));
            } catch (Exception error) {
                showRequestError(error);
            }
        });
    }

    private void scrollDashboard(double position) {
        if (!ensureConfigured()) return;
        clearError();
        network.execute(() -> {
            try {
                request("POST", "/api/display/scroll", new JSONObject().put("position", position), true);
            } catch (Exception error) {
                showRequestError(error);
            }
        });
    }

    private void askAlfred(String query) {
        String trimmed = query == null ? "" : query.trim();
        if (trimmed.isEmpty()) {
            showError("Enter a question first.");
            return;
        }
        if (!ensureConfigured()) return;
        clearError();
        setBusy(true);
        network.execute(() -> {
            try {
                JSONObject body = new JSONObject().put("query", trimmed);
                JSONObject result = request("POST", "/api/assistant/query", body, true);
                runOnUiThread(() -> {
                    queryInput.setText("");
                    answerText.setText(result.optString("answer", ""));
                    setBusy(false);
                });
            } catch (Exception error) {
                showRequestError(error);
            }
        });
    }

    private boolean ensureConfigured() {
        if (!token().isEmpty()) return true;
        showError("Alfred needs its access key.");
        showSettings();
        return false;
    }

    private void showSettings() {
        int padding = Math.round(22 * getResources().getDisplayMetrics().density);
        LinearLayout form = new LinearLayout(this);
        form.setOrientation(LinearLayout.VERTICAL);
        form.setPadding(padding, padding / 2, padding, 0);

        TextView serverLabel = new TextView(this);
        serverLabel.setText("UNO Q address");
        EditText serverInput = new EditText(this);
        serverInput.setSingleLine(true);
        serverInput.setText(serverUrl());

        TextView tokenLabel = new TextView(this);
        tokenLabel.setText("TV_REMOTE_TOKEN from Alfred's .env");
        tokenLabel.setPadding(0, padding / 2, 0, 0);
        EditText tokenInput = new EditText(this);
        tokenInput.setSingleLine(true);
        tokenInput.setText(token());

        form.addView(serverLabel);
        form.addView(serverInput);
        form.addView(tokenLabel);
        form.addView(tokenInput);
        new AlertDialog.Builder(this)
                .setTitle("Connect to Alfred")
                .setView(form)
                .setMessage("Keep the phone and UNO Q on the same trusted Wi-Fi.")
                .setNegativeButton("Cancel", null)
                .setPositiveButton("Save", (dialog, which) -> {
                    String server = normalizeServerUrl(serverInput.getText().toString());
                    String accessToken = tokenInput.getText().toString().trim();
                    preferences.edit().putString(SERVER_KEY, server).putString(TOKEN_KEY, accessToken).apply();
                    checkServer();
                })
                .show();
    }

    private String serverUrl() {
        String saved = normalizeServerUrl(preferences.getString(SERVER_KEY, DEFAULT_SERVER));
        // Android's regular DNS resolver does not consistently perform mDNS
        // lookup for .local names. Transparently migrate existing installs.
        if (saved.equalsIgnoreCase(LEGACY_SERVER)) {
            preferences.edit().putString(SERVER_KEY, DEFAULT_SERVER).apply();
            return DEFAULT_SERVER;
        }
        return saved;
    }

    private String normalizeServerUrl(String value) {
        String server = value == null ? "" : value.trim().replaceAll("/+$", "");
        if (server.isEmpty()) return DEFAULT_SERVER;
        if (!server.matches("(?i)^https?://.*")) server = "http://" + server;
        // Repair the common phone-keyboard typo 192.168.1.41.8080.
        server = server.replaceFirst("^(https?://(?:\\d+\\.){3}\\d+)\\.(\\d+)$", "$1:$2");
        return server;
    }

    private String token() {
        return preferences.getString(TOKEN_KEY, "").trim();
    }

    private JSONObject request(String method, String path, JSONObject body, boolean authenticated) throws Exception {
        String server = serverUrl();
        try {
            return requestAt(server, method, path, body, authenticated);
        } catch (IOException firstError) {
            String discovered = discoverAlfred(server);
            if (discovered == null) throw firstError;
            preferences.edit().putString(SERVER_KEY, discovered).apply();
            return requestAt(discovered, method, path, body, authenticated);
        }
    }

    private JSONObject requestAt(String server, String method, String path, JSONObject body, boolean authenticated) throws Exception {
        HttpURLConnection connection = (HttpURLConnection) new URL(server + path).openConnection();
        connection.setRequestMethod(method);
        connection.setConnectTimeout(5_000);
        connection.setReadTimeout(25_000);
        connection.setUseCaches(false);
        connection.setRequestProperty("Accept", "application/json");
        if (authenticated) {
            connection.setRequestProperty("X-Alfred-Remote", "1");
            connection.setRequestProperty("X-Alfred-Remote-Token", token());
        }
        if (body != null) {
            byte[] bytes = body.toString().getBytes(StandardCharsets.UTF_8);
            connection.setDoOutput(true);
            connection.setRequestProperty("Content-Type", "application/json; charset=utf-8");
            connection.setFixedLengthStreamingMode(bytes.length);
            try (OutputStream output = connection.getOutputStream()) {
                output.write(bytes);
            }
        }

        int status = connection.getResponseCode();
        InputStream stream = status >= 200 && status < 300 ? connection.getInputStream() : connection.getErrorStream();
        StringBuilder text = new StringBuilder();
        if (stream != null) {
            try (BufferedReader reader = new BufferedReader(new InputStreamReader(stream, StandardCharsets.UTF_8))) {
                String line;
                while ((line = reader.readLine()) != null) text.append(line);
            }
        }
        connection.disconnect();
        JSONObject result = text.length() == 0 ? new JSONObject() : new JSONObject(text.toString());
        if (status < 200 || status >= 300) {
            throw new IllegalStateException(result.optString("error", "Alfred returned HTTP " + status));
        }
        return result;
    }

    private String discoverAlfred(String failedServer) {
        Set<String> candidates = new LinkedHashSet<>();
        candidates.add(DEFAULT_SERVER);
        candidates.add(LEGACY_SERVER);
        try {
            Enumeration<NetworkInterface> interfaces = NetworkInterface.getNetworkInterfaces();
            while (interfaces.hasMoreElements()) {
                Enumeration<InetAddress> addresses = interfaces.nextElement().getInetAddresses();
                while (addresses.hasMoreElements()) {
                    InetAddress address = addresses.nextElement();
                    if (!(address instanceof Inet4Address) || address.isLoopbackAddress() || !address.isSiteLocalAddress()) continue;
                    String host = address.getHostAddress();
                    int dot = host.lastIndexOf('.');
                    if (dot < 0) continue;
                    String prefix = host.substring(0, dot + 1);
                    for (int suffix = 1; suffix < 255; suffix++) {
                        candidates.add("http://" + prefix + suffix + ":8080");
                    }
                }
            }
        } catch (Exception ignored) { }
        candidates.remove(failedServer);

        ExecutorService probes = Executors.newFixedThreadPool(32);
        CompletionService<String> completed = new ExecutorCompletionService<>(probes);
        for (String candidate : candidates) {
            completed.submit(() -> isAlfred(candidate) ? candidate : null);
        }
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(6);
        try {
            for (int count = 0; count < candidates.size(); count++) {
                long remaining = deadline - System.nanoTime();
                if (remaining <= 0) break;
                Future<String> result = completed.poll(remaining, TimeUnit.NANOSECONDS);
                if (result == null) break;
                String found = result.get();
                if (found != null) return found;
            }
        } catch (Exception ignored) {
        } finally {
            probes.shutdownNow();
        }
        return null;
    }

    private boolean isAlfred(String server) {
        HttpURLConnection connection = null;
        try {
            connection = (HttpURLConnection) new URL(server + "/api/tv/status").openConnection();
            connection.setConnectTimeout(650);
            connection.setReadTimeout(650);
            if (connection.getResponseCode() != 200) return false;
            try (BufferedReader reader = new BufferedReader(new InputStreamReader(connection.getInputStream(), StandardCharsets.UTF_8))) {
                StringBuilder text = new StringBuilder();
                String line;
                while ((line = reader.readLine()) != null) text.append(line);
                return "Alfred".equals(new JSONObject(text.toString()).optString("name"));
            }
        } catch (Exception ignored) {
            return false;
        } finally {
            if (connection != null) connection.disconnect();
        }
    }

    private void clearError() {
        errorText.setText("");
        errorText.setVisibility(View.GONE);
    }

    private void showError(String message) {
        runOnUiThread(() -> {
            errorText.setText("ERROR: " + message);
            errorText.setVisibility(View.VISIBLE);
        });
    }

    private void showRequestError(Exception error) {
        runOnUiThread(() -> {
            setListening(false);
            setBusy(false);
            String message = error.getMessage() == null ? "Could not reach Alfred." : error.getMessage();
            showError(message);
            checkServer();
        });
    }
}
