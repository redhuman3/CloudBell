import pygame
import random

# Ініціалізація Pygame
pygame.init()

# Розміри екрану
width, height = 800, 600
screen = pygame.display.set_mode((width, height))

# Назва гри
pygame.display.set_caption("Гарна Змійка")

# Завантаження спрайтів
snake_img = pygame.image.load("snake.png")
apple_img = pygame.image.load("apple.png")
background_img = pygame.image.load("background.jpg")  # Завантаження фону

# Масштабування спрайтів до розміру клітинки (40x40)
snake_block = 40
snake_img = pygame.transform.scale(snake_img, (snake_block, snake_block))
apple_img = pygame.transform.scale(apple_img, (snake_block, snake_block))
background_img = pygame.transform.scale(background_img, (width, height))  # Масштабування фону

# Завантаження звуків
eat_sound = pygame.mixer.Sound("eat.mp3")
game_over_sound = pygame.mixer.Sound("game_over.mp3")

# Колір для тексту
white = (255, 255, 255)
red = (213, 50, 80)
black = (0, 0, 0)

# Шрифт
font_style = pygame.font.SysFont("bahnschrift", 25)
score_font = pygame.font.SysFont("comicsansms", 35)

# Функція для відображення рахунку
def your_score(score):
    value = score_font.render("Ваш рахунок: " + str(score), True, white)
    screen.blit(value, [10, 10])

# Функція для відображення повідомлення
def message(msg, color, y_offset):
    mesg = font_style.render(msg, True, color)
    screen.blit(mesg, [width / 6, height / 3 + y_offset])

# Меню гри
def game_menu():
    menu = True
    while menu:
        screen.fill(black)
        message("Гарна Змійка", white, 0)  # Головний напис
        message("Натисніть S для старту", red, 40)  # Інструкція
        message("Натисніть Q для виходу", red, 80)  # Інструкція
        pygame.display.update()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                quit()
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_s:
                    menu = False
                if event.key == pygame.K_q:
                    pygame.quit()
                    quit()

# Основна функція гри
def gameLoop():
    game_over = False
    game_close = False

    # Початкові координати змійки
    x1 = width / 2
    y1 = height / 2

    # Зміна координат
    x1_change = 0
    y1_change = 0

    snake_list = []
    length_of_snake = 1

    # Координати яблука
    apple_x = round(random.randrange(0, width - snake_block) / snake_block) * snake_block
    apple_y = round(random.randrange(0, height - snake_block) / snake_block) * snake_block

    clock = pygame.time.Clock()
    speed = 7  # Повільніша швидкість змійки (кадри за секунду)

    while not game_over:

        while game_close:
            screen.fill(black)
            pygame.mixer.Sound.play(game_over_sound)
            message("Програш! Натисніть Q для виходу", red, 0)
            message("Або C для повтору", red, 40)
            your_score(length_of_snake - 1)
            pygame.display.update()

            for event in pygame.event.get():
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_q:
                        game_over = True
                        game_close = False
                    if event.key == pygame.K_c:
                        gameLoop()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                game_over = True
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_LEFT and x1_change == 0:
                    x1_change = -snake_block
                    y1_change = 0
                elif event.key == pygame.K_RIGHT and x1_change == 0:
                    x1_change = snake_block
                    y1_change = 0
                elif event.key == pygame.K_UP and y1_change == 0:
                    y1_change = -snake_block
                    x1_change = 0
                elif event.key == pygame.K_DOWN and y1_change == 0:
                    y1_change = snake_block
                    x1_change = 0

        if x1 >= width or x1 < 0 or y1 >= height or y1 < 0:
            game_close = True
        x1 += x1_change
        y1 += y1_change
        screen.blit(background_img, (0, 0))  # Малювання фону
        screen.blit(apple_img, (apple_x, apple_y))

        # Малювання змійки
        snake_head = [x1, y1]
        snake_list.append(snake_head)
        if len(snake_list) > length_of_snake:
            del snake_list[0]

        for x in snake_list[:-1]:
            if x == snake_head:
                game_close = True

        for block in snake_list:
            screen.blit(snake_img, (block[0], block[1]))

        your_score(length_of_snake - 1)
        pygame.display.update()

        # Перевірка, чи змійка "з'їла" яблуко
        if abs(x1 - apple_x) < snake_block and abs(y1 - apple_y) < snake_block:
            apple_x = round(random.randrange(0, width - snake_block) / snake_block) * snake_block
            apple_y = round(random.randrange(0, height - snake_block) / snake_block) * snake_block
            length_of_snake += 1
            pygame.mixer.Sound.play(eat_sound)

        clock.tick(speed)

    pygame.quit()
    quit()

# Запуск меню
game_menu()
gameLoop()