<?php
namespace local_coderunner_agent;

defined('MOODLE_INTERNAL') || die();

class agent_api {

    private string $base_url;

    public function __construct() {
        $configured = get_config('local_coderunner_agent', 'agent_url');
        $this->base_url = !empty($configured) ? $configured : 'http://cra-agent:8001';
    }

    /**
     * @return array{status: int, body: string, content_disposition: string}
     */
    public function get(string $endpoint, array $params = []): array {
        $url = $this->base_url . $endpoint;
        if ($params) {
            $url .= '?' . http_build_query($params);
        }
        $ch = curl_init($url);
        $accept = (strpos($endpoint, '/export') !== false) ? '*/*' : 'application/json';
        curl_setopt_array($ch, [
            CURLOPT_RETURNTRANSFER => true,
            CURLOPT_HEADER         => true,
            CURLOPT_TIMEOUT        => 30,
            CURLOPT_HTTPHEADER     => ['Accept: ' . $accept],
        ]);
        $response = curl_exec($ch);
        $status = (int) curl_getinfo($ch, CURLINFO_HTTP_CODE);
        $header_size = (int) curl_getinfo($ch, CURLINFO_HEADER_SIZE);
        curl_close($ch);

        if ($response === false) {
            return ['status' => 0, 'body' => '', 'content_disposition' => ''];
        }

        $headers_raw = substr($response, 0, $header_size);
        $body = substr($response, $header_size);

        return [
            'status' => $status,
            'body' => $body,
            'content_disposition' => self::parse_content_disposition($headers_raw),
        ];
    }

    public function post(string $endpoint, string $json_body): array {
        $url = $this->base_url . $endpoint;
        $ch  = curl_init($url);
        curl_setopt_array($ch, [
            CURLOPT_RETURNTRANSFER => true,
            CURLOPT_TIMEOUT        => 60,
            CURLOPT_POST           => true,
            CURLOPT_POSTFIELDS     => $json_body,
            CURLOPT_HTTPHEADER     => [
                'Content-Type: application/json',
                'Accept: application/json',
            ],
        ]);
        $body   = curl_exec($ch);
        $status = curl_getinfo($ch, CURLINFO_HTTP_CODE);
        curl_close($ch);
        return ['status' => (int) $status, 'body' => $body ?: ''];
    }

    public function patch(string $endpoint, string $json_body): array {
        $url = $this->base_url . $endpoint;
        $ch  = curl_init($url);
        curl_setopt_array($ch, [
            CURLOPT_RETURNTRANSFER => true,
            CURLOPT_TIMEOUT        => 30,
            CURLOPT_CUSTOMREQUEST  => 'PATCH',
            CURLOPT_POSTFIELDS     => $json_body,
            CURLOPT_HTTPHEADER     => [
                'Content-Type: application/json',
                'Accept: application/json',
            ],
        ]);
        $body   = curl_exec($ch);
        $status = curl_getinfo($ch, CURLINFO_HTTP_CODE);
        curl_close($ch);
        return ['status' => (int) $status, 'body' => $body ?: ''];
    }

    private static function parse_content_disposition(string $headers): string {
        foreach (preg_split('/\r\n|\n|\r/', $headers) as $line) {
            if (stripos($line, 'Content-Disposition:') === 0) {
                return trim(substr($line, strlen('Content-Disposition:')));
            }
        }
        return '';
    }
}
