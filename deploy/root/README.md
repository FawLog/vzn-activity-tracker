# Ограниченный root-доступ для VZN

Эти сценарии предназначены только для отдельно согласованного production deployment. До зелёного CI и явного разрешения их нельзя устанавливать или запускать.

`install-vzn-activity-tracker` не принимает аргументы, читает только фиксированный root-owned staging, повторно проверяет SHA-256 и соответствие одного Git-коммита всем артефактам. Он предназначен только для первой установки: существующий application root является ошибкой. Обновления выполняет отдельный root-owned `vzn-update`, подготовленный `stage-vzn-artifacts --update`; он сохраняет `.env`, SQLite и предыдущий release для rollback. Ни один из сценариев не собирает код, не устанавливает пакеты, не вызывает Docker prune и не изменяет firewall или чужие конфигурации. Перед изменениями сценарии консервативно оценивают пик распаковки Docker-образа и сохраняют не менее 2 ГиБ свободного места.

Staging создаётся через временный root-owned каталог и становится активным только после полной проверки. Сначала helper копирует входные артефакты в неизменяемый непривилегированным пользователем root-owned снимок, затем проверяет и распаковывает только этот снимок. Установщик сначала формирует `.env` во временном каталоге `/run`, затем помечает изменяемое состояние файлом `.vzn-installing`. При обычной ошибке или сигнале он останавливает только Compose-проект VZN, изолирует только созданные VZN-файлы в `/var/backups/vzn-activity-tracker/` и возвращает Nginx к исходному состоянию. После аварийной перезагрузки повторный запуск автоматически распознаёт только marker того же CI-коммита, сохраняет частичное состояние для разбора и начинает чистую попытку. Неизвестный или чужой `/srv/vzn-activity-tracker` автоматически не изменяется.

Хостовые IP и пути сертификата читаются из не хранящегося в Git файла `/etc/vzn-activity-tracker/deploy.conf`, который должен принадлежать `root:root` и иметь mode `0600`. Формат описан в `DEPLOYMENT.md`.

## Read-only аудит диска

Владелец VPS может проверить сценарий и установить его из доверенной локальной копии репозитория:

```sh
sudo install -o root -g root -m 0755 "$PWD/deploy/root/audit-vps-storage" /usr/local/sbin/vzn-audit-storage
sudo /usr/local/sbin/vzn-audit-storage
```

Сценарий ничего не удаляет и не вызывает prune.

## Вариант A — разовый запуск владельцем

После проверки точного успешного CI-коммита владелец вычисляет SHA-256 staging-helper именно из проверенного deployment-артефакта, сравнивает его с заранее зафиксированным значением, устанавливает root-owned копию, передаёт ей абсолютный путь к скачанным артефактам и запускает установленный no-argument deployer:

```sh
printf '%s  %s\n' '<reviewed-helper-sha256>' '/absolute/private/path/to/reviewed-source/deploy/root/stage-vzn-artifacts' | sha256sum --check -
sudo install -o root -g root -m 0755 /absolute/private/path/to/reviewed-source/deploy/root/stage-vzn-artifacts /usr/local/sbin/vzn-stage-vzn-artifacts
printf '%s  %s\n' '<reviewed-helper-sha256>' '/usr/local/sbin/vzn-stage-vzn-artifacts' | sudo sha256sum --check -
sudo /usr/local/sbin/vzn-stage-vzn-artifacts /absolute/private/path/to/artifacts
sudo /usr/local/sbin/vzn-deploy
```

Последний вызов отдельно и без отображения ввода запросит новый пароль администратора. Пароль не передаётся аргументом.

## Вариант B — временное узкое правило sudoers

Владелец выполняет staging из варианта A. Staging-helper устанавливает root-owned deployer и root-owned helper управления sudoers. Команда `grant` определяет только фактического вызывающего пользователя из защищённого `SUDO_USER`, проверяет имя системного пользователя, вычисляет SHA-256 root-owned deployer и атомарно устанавливает правило только для запуска этого файла без аргументов:

```sh
sudo /usr/local/sbin/vzn-manage-sudoers grant
sudo -k
sudo -n -l
sudo -n /usr/local/sbin/vzn-deploy
```

Нельзя разрешать пользовательскую копию сценария, пользовательский Compose-файл, произвольные аргументы или добавление пользователя в группу Docker.

После установки владелец отзывает правило и проверяет, что беспарольный запуск невозможен:

```sh
sudo /usr/local/sbin/vzn-manage-sudoers revoke
sudo -k
sudo -n /usr/local/sbin/vzn-deploy
```

Последняя команда должна отказать без пароля. Удаление staging или артефактов в эту процедуру намеренно не включено.

## Обновление существующей VZN-инсталляции

Владелец сначала сверяет digest новой версии `stage-vzn-artifacts` из reviewed deployment artifact и обновляет только root-owned helper. Затем helper создаёт отдельный root-owned update staging, устанавливает `vzn-update` и обновляет root-owned helper управления sudoers; исходный staging первой установки не изменяется.

```sh
sudo install -o root -g root -m 0755 \
  /absolute/private/path/to/reviewed-source/deploy/root/stage-vzn-artifacts \
  /usr/local/sbin/vzn-stage-vzn-artifacts
sudo /usr/local/sbin/vzn-stage-vzn-artifacts --update /absolute/private/path/to/artifacts
sudo /usr/local/sbin/vzn-update
```

Для временного запуска update без интерактивного пароля доступна отдельная узкая пара команд. Она разрешает только digest-pinned `vzn-update` без аргументов и собственный отзыв этого правила; Docker-доступ и произвольные root-команды не выдаются:

```sh
sudo /usr/local/sbin/vzn-manage-sudoers grant-update
sudo -n /usr/local/sbin/vzn-update
sudo -n /usr/local/sbin/vzn-manage-sudoers revoke-update
```

`vzn-update` не принимает аргументы и не меняет Nginx. Он создаёт проверенную online-backup SQLite до запуска новой версии. При неуспехе он восстанавливает backup через SQLite Backup API и предыдущие `.env`, Compose и frontend release; при неустранимом прерывании оставляет marker для ручного review вместо небезопасного автоматического продолжения. Полная процедура восстановления приведена в `DEPLOYMENT.md`.
