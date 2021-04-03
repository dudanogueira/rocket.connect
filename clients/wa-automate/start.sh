npx @open-wa/wa-automate    -w 'http://127.0.0.1:8000/connector/4333bd76-519f-4fe8-b51a-a228b29a4e19' \
                                -e 'http://127.0.0.1:8000/connector/4333bd76-519f-4fe8-b51a-a228b29a4e19' \
                                --kill-client-on-logout \
                                --event-mode \
                                --delete-session-data-on-logout \
                                --skip-save-postman-collection \
                                --disable-spins \
                                --keep-alive \
                                --block-crash-logs \
                                --session-id 'test-session'
                                #--stats \
                                #--throw-on-expired-session-data
                                #--popup