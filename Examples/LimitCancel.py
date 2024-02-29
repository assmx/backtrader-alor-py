import logging
from datetime import datetime

import backtrader as bt

from BackTraderAlor.ALStore import ALStore  # Хранилище Alor
from MarketPy.Schedule import MOEXStocks, MOEXFutures  # Расписания торгов фондового/срочного рынков


# noinspection PyShadowingNames,PyProtectedMember
class LimitCancel(bt.Strategy):
    """
    Выставляем заявку на покупку на n% ниже цены закрытия
    Если за 1 бар заявка не срабатывает, то закрываем ее
    Если срабатывает, то закрываем позицию. Неважно, с прибылью или убытком
    """
    logger = logging.getLogger('BackTraderAlor.LimitCancel')  # Будем вести лог
    params = (  # Параметры торговой системы
        ('LimitPct', 1),  # Заявка на покупку на n% ниже цены закрытия
    )

    def __init__(self):
        """Инициализация торговой системы"""
        self.live = False  # Сначала будут приходить исторические данные, затем перейдем в режим реальной торговли
        self.order = None  # Заявка на вход/выход из позиции

    def next(self):
        """Получение следующего исторического/нового бара"""
        if not self.live:  # Если не в режиме реальной торговли
            return  # то выходим, дальше не продолжаем
        self.logger.info(f'Получен бар: {self.data._name} - {bt.TimeFrame.Names[self.data.p.timeframe]} {self.data.p.compression} - {bt.num2date(self.data.datetime[0]):%d.%m.%Y %H:%M:%S} - Open = {self.data.open[0]}, High = {self.data.high[0]}, Low = {self.data.low[0]}, Close = {self.data.close[0]}, Volume = {self.data.volume[0]}')
        if self.order and self.order.status == bt.Order.Submitted:  # Если заявка не исполнена (отправлена брокеру)
            return  # то ждем исполнения, выходим, дальше не продолжаем
        if not self.position:  # Если позиции нет
            if self.order and self.order.status == bt.Order.Accepted:  # Если заявка не исполнена (принята брокером)
                self.cancel(self.order)  # то снимаем ее
            limit_price = self.data.close[0] * (1 - self.p.LimitPct / 100)  # На n% ниже цены закрытия
            self.order = self.buy(exectype=bt.Order.Limit, price=limit_price)  # Лимитная заявка на покупку
            self.logger.info(f'Заявка {self.order.ref} - {"Покупка" if self.order.isbuy else "Продажа"} {self.order.data._name} {self.order.size} @ {self.order.price} cоздана и отправлена на биржу {self.order.data.exchange}')
        else:  # Если позиция есть
            self.order = self.close()  # Заявка на закрытие позиции (заявки) по рыночной цене

    def notify_data(self, data, status, *args, **kwargs):
        """Изменение статуса приходящих баров"""
        data_status = data._getstatusname(status)  # Получаем статус (только при live_bars=True)
        self.live = data_status == 'LIVE'  # Режим реальной торговли
        self.logger.info(data_status)

    def notify_order(self, order):
        """Изменение статуса заявки"""
        exchange = order.data.exchange  # Биржа
        if order.status in (bt.Order.Created, bt.Order.Submitted, bt.Order.Accepted):  # Если заявка создана, отправлена брокеру, принята брокером (не исполнена)
            self.logger.info(f'Заявка {order.ref} на бирже {exchange} со статусом {order.getstatusname()}')
        elif order.status in (bt.Order.Canceled, bt.Order.Margin, bt.Order.Rejected, bt.Order.Expired):  # Если заявка отменена, нет средств, заявка отклонена брокером, снята по времени (снята)
            self.logger.info(f'Заявка {order.ref} на бирже {exchange} отменена со статусом {order.getstatusname()}')
        elif order.status == bt.Order.Partial:  # Если заявка частично исполнена
            self.logger.info(f'Заявка {order.ref} на бирже {exchange} частично исполнена со статусом {order.getstatusname()}')
        elif order.status == bt.Order.Completed:  # Если заявка полностью исполнена
            self.logger.info(f'Заявка на {"покупку" if order.isbuy() else "продажу"} на бирже {exchange} исполнена по цене {order.executed.price}, Стоимость {order.executed.value}, Комиссия {order.executed.comm}')
            self.order = None  # Сбрасываем заявку на вход в позицию

    def notify_trade(self, trade):
        """Изменение статуса позиции"""
        if trade.isclosed:  # Если позиция закрыта
            self.logger.info(f'Позиция закрыта. Прибыль = {trade.pnl:.2f}, С учетом комиссий = {trade.pnlcomm:.2f}')


if __name__ == '__main__':  # Точка входа при запуске этого скрипта
    symbol = 'TQBR.SBER'  # Тикер в формате: <Код режима торгов>.<Тикер>
    # schedule = MOEXStocks()  # Расписание торгов фондового рынка
    # symbol = 'RFUD.SI-3.24'  # Для фьючерсов: <RFUD>.<Код тикера заглавными буквами>-<Месяц экспирации: 3, 6, 9, 12>.<Последние 2 цифры года>
    # symbol = 'RFUD.RTS-3.24'
    # schedule = MOEXFutures()  # Расписание торгов срочного рынка
    # noinspection PyArgumentList
    cerebro = bt.Cerebro(stdstats=False, quicknotify=True)  # Инициируем "движок" BackTrader. Стандартная статистика сделок и кривой доходности не нужна. События принимаем без задержек
    store = ALStore()  # Хранилище Alor

    logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',  # Формат сообщения
                        datefmt='%d.%m.%Y %H:%M:%S',  # Формат даты
                        level=logging.DEBUG,  # Уровень логируемых событий NOTSET/DEBUG/INFO/WARNING/ERROR/CRITICAL
                        handlers=[logging.FileHandler('LimitCancel.log'), logging.StreamHandler()])  # Лог записываем в файл и выводим на консоль
    logging.Formatter.converter = lambda *args: datetime.now(tz=store.provider.tz_msk).timetuple()  # В логе время указываем по МСК
    logging.getLogger('asyncio').setLevel(logging.CRITICAL + 1)
    logging.getLogger('urllib3').setLevel(logging.CRITICAL + 1)
    logging.getLogger('websockets').setLevel(logging.CRITICAL + 1)

    broker = store.getbroker(use_positions=False)  # Брокер Alor
    # noinspection PyArgumentList
    cerebro.setbroker(broker)  # Устанавливаем брокера
    data = store.getdata(dataname=symbol, timeframe=bt.TimeFrame.Minutes, compression=1, account_id=1, live_bars=True)  # Исторические и новые минутные бары за все время по подписке
    # data = store.getdata(dataname=symbol, timeframe=bt.TimeFrame.Minutes, compression=1, schedule=schedule, live_bars=True)  # Исторические и новые минутные бары за все время по расписанию
    cerebro.adddata(data)  # Добавляем данные
    cerebro.addsizer(bt.sizers.FixedSize, stake=10)  # Кол-во акций в штуках для покупки/продажи
    # cerebro.addsizer(bt.sizers.FixedSize, stake=1)  # Кол-во фьючерсов в штуках для покупки/продажи
    cerebro.addstrategy(LimitCancel, LimitPct=1)  # Добавляем торговую систему с лимитным входом в n%
    cerebro.run()  # Запуск торговой системы
